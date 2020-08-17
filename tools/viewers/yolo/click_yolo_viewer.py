import click

from .yolo_viewer import main


@click.command()
@click.argument("input_folders", type=str, nargs=-1)
@click.option("-sample_size", type=click.FloatRange(0.0, 1.0), default=1.0)
def yolo(input_folders, sample_size):
    """
    Darknet YOLO label viewer

    \b

    This viewer allows you to visualize labels in Darknet YOLO format.
    Specify -sample_size [0.0-1.0] to only show only a smaller subset of all labels.

    \b
    Input:
    input_folder_1
        ├── images
           ├── img_x.jpeg
           ├── img_y.jpeg
           └── img_z.jpeg
        └── labels
           ├── img_x.txt
           ├── img_y.txt
           └── img_z.txt


    """
    click.echo("[LOG] Running Darknet Yolo label viewer")
    main(input_folders, sample_size)


if __name__ == "__main__":
    click.echo(
        "[LOG] This sub-module is not meant to be run as a stand-alone script. Please refer to\n $ fsoco --help"
    )
