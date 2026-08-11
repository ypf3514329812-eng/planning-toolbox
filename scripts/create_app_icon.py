"""Create the Planning Toolbox desktop icon in PNG and Windows ICO formats."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
SIZE = 1024


def create_icon() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), "#F1EEE6")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((48, 48, 976, 976), radius=178, outline="#566D8E", width=32)

    draw.polygon(
        [(174, 278), (448, 154), (820, 274), (722, 510), (466, 646), (170, 544)],
        fill="#8197B5",
        outline="#566D8E",
    )
    draw.line(
        [(174, 278), (448, 154), (820, 274), (722, 510), (466, 646), (170, 544), (174, 278)],
        fill="#566D8E",
        width=18,
        joint="curve",
    )

    draw.polygon(
        [(466, 646), (722, 510), (852, 646), (650, 864), (364, 794)],
        fill="#829A8B",
        outline="#607A6A",
    )
    draw.line(
        [(466, 646), (722, 510), (852, 646), (650, 864), (364, 794), (466, 646)],
        fill="#607A6A",
        width=18,
        joint="curve",
    )

    draw.polygon(
        [(170, 544), (466, 646), (364, 794), (148, 704)],
        fill="#D7A39E",
        outline="#A96761",
    )
    draw.line(
        [(170, 544), (466, 646), (364, 794), (148, 704), (170, 544)],
        fill="#A96761",
        width=18,
        joint="curve",
    )

    paper = "#FBFAF6"
    dark = "#3E536E"
    draw.line([(198, 348), (444, 236), (762, 336)], fill=paper, width=14, joint="curve")
    draw.line([(260, 592), (466, 664), (690, 548)], fill=paper, width=14, joint="curve")
    draw.line([(466, 248), (466, 740)], fill=dark, width=12)
    draw.line([(246, 392), (704, 548)], fill=dark, width=12)
    draw.ellipse((438, 618, 494, 674), fill=paper, outline=dark, width=12)
    draw.line([(466, 606), (466, 686)], fill=dark, width=10)
    draw.line([(426, 646), (506, 646)], fill=dark, width=10)
    return image


if __name__ == "__main__":
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    icon = create_icon()
    icon.save(ASSET_DIR / "planning_toolbox_icon.png", format="PNG")
    icon.save(
        ASSET_DIR / "planning_toolbox.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Created {ASSET_DIR / 'planning_toolbox_icon.png'}")
    print(f"Created {ASSET_DIR / 'planning_toolbox.ico'}")
