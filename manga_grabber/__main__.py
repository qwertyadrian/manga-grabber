import asyncio
import pathlib

import click

from .export import download_title


@click.command()
@click.argument("title_url", type=str)
@click.argument("output_dir", type=click.Path(file_okay=False, path_type=pathlib.Path))
@click.option("--branch-id", type=int, default=-1, help="ID of translation branch if applicable")
@click.option("--token", type=str, default=None, envvar="TOKEN", help="Authentication token if required")
@click.option("--cbz", is_flag=True, default=False, help="Export title as CBZ")
@click.option("--pdf", is_flag=True, default=False, help="Export title as PDF")
@click.option("--epub", is_flag=True, default=False, help="Export title as EPUB")
@click.option(
    "--save-mode",
    type=click.Choice(["all", "volume", "chapter"], case_sensitive=False),
    default="all",
    help="Save mode for downloaded chapters",
)
@click.option(
    "--from-chapter",
    type=float,
    default=0,
    help="Chapter number to start downloading from",
)
@click.option(
    "--from-volume",
    type=int,
    default=0,
    help="Volume number to start downloading from",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose output")
@click.version_option()
def main(
    title_url: str,
    output_dir: pathlib.Path,
    branch_id: int,
    token: str | None,
    cbz: bool,
    pdf: bool,
    epub: bool,
    save_mode: str,
    from_chapter: int | float,
    from_volume: int,
    verbose: bool,
):
    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    asyncio.run(
        download_title(
            title_url,
            output_dir,
            branch_id=branch_id,
            token=token,
            cbz=cbz,
            pdf=pdf,
            epub=epub,
            save_mode=save_mode,
            from_chapter=from_chapter,
            from_volume=from_volume,
        )
    )


if __name__ == "__main__":
    main()
