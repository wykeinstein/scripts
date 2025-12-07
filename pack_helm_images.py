#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

DEFAULT_MANIFEST = "rendered.yaml"
DEFAULT_IMAGES_FILE = "images.txt"
DEFAULT_IMAGES_TAR = "images.tar"


def run(cmd, **kwargs):
    """Run a shell command, print it, and fail on error."""
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def render_chart(chart_path, values_file, manifest):
    """Run `helm template` and write manifest to file."""
    release_name = "offline"  # 固定一个名字就够用了
    with manifest.open("w", encoding="utf-8") as f:
        cmd = ["helm", "template", release_name, chart_path]
        if values_file:
            cmd.extend(["-f", values_file])
        run(cmd, stdout=f)


def extract_images_with_yq(manifest, images_file):
    """Use yq v4 to extract all .image fields and return sorted unique list.

    这里用 check_output + universal_newlines=True，兼容 Python 3.5。
    """
    try:
        output = subprocess.check_output(
            ["yq", "eval", "-r", '.. | .image? // "" | select(. != "")', str(manifest)],
            universal_newlines=True,  # 相当于 text=True，在老版本里也可用
        )
    except subprocess.CalledProcessError as e:
        sys.stderr.write("ERROR: failed to run yq: {}\n".format(e))
        sys.exit(e.returncode)

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    unique_sorted = sorted(set(lines))

    images_file.write_text(
        "\n".join(unique_sorted) + ("\n" if unique_sorted else ""),
        encoding="utf-8",
    )

    return unique_sorted


def pull_images(images):
    """docker pull all images."""
    for img in images:
        print("Pulling {}".format(img))
        run(["docker", "pull", img])


def save_images(images, tar_path):
    """docker save -o images.tar <images...>"""
    if not images:
        print("No images found, skip docker save")
        return
    cmd = ["docker", "save", "-o", str(tar_path)] + images
    run(cmd)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "From a Helm chart, collect all container images, pull them and save to a tar file."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--chart",
        required=True,
        help="Path to chart directory or repo/chartname",
    )
    parser.add_argument(
        "-f",
        "--values",
        help="Values YAML file for the chart (optional)",
    )
    parser.add_argument(
        "-m",
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="Path to render manifest output file",
    )
    parser.add_argument(
        "-i",
        "--images-file",
        default=DEFAULT_IMAGES_FILE,
        help="Path to image list output file",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_IMAGES_TAR,
        help="Path to output tar file (docker save)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    chart_path = args.chart
    values_file = args.values
    manifest = Path(args.manifest)
    images_file = Path(args.images_file)
    tar_path = Path(args.output)

    print("Chart path   : {}".format(chart_path))
    print("Values file  : {}".format(values_file if values_file else "(none)"))
    print("Manifest file: {}".format(manifest))
    print("Images file  : {}".format(images_file))
    print("Output tar   : {}".format(tar_path))

    # 1. 渲染 chart
    render_chart(chart_path, values_file, manifest)

    # 2. 提取镜像列表
    images = extract_images_with_yq(manifest, images_file)
    if not images:
        print("No images found in rendered manifest.")
        sys.exit(1)

    print("Found images:")
    for img in images:
        print("  {}".format(img))

    # 3. 拉镜像
    pull_images(images)

    # 4. 打包镜像
    save_images(images, tar_path)

    print("Done. Images saved to {}".format(tar_path))


if __name__ == "__main__":
    main()

