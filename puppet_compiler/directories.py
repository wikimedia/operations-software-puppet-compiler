"""Classes for managing filsystem objects"""
from pathlib import Path
from typing import Union


# pylint: disable=too-few-public-methods
class FHS:
    """Object to manage the file system hieracry"""

    base_dir: Path
    prod_dir: Path
    change_dir: Path
    diff_dir: Path
    output_dir: Path

    @classmethod
    def setup(cls, change_id: int, job_id: int, base: Union[str, Path]) -> None:
        """Setup the base file system"""
        base_dir = Path(base) if isinstance(base, str) else base
        cls.base_dir = base_dir / str(job_id)
        cls.prod_dir = cls.base_dir / "production"
        cls.change_dir = cls.base_dir / "change"
        cls.diff_dir = cls.base_dir / "diffs"
        cls.output_dir = base_dir / "output" / str(change_id) / str(job_id)


class HostFiles:
    """Class to manage host files"""

    def __init__(self, hostname: str) -> None:
        self.hostname = hostname
        self.outdir = FHS.output_dir / self.hostname

    def file_for(self, env: str, what: str) -> Path:
        """Return the path of a file type in a specific environment

        Argumnets:
            env: The envorinment to search in
            what: The type of file to look for

        Returns:
            Path: The file path to the file

        """
        if env in ["prod", "change"]:
            suffix = ""
        else:
            suffix = "-%s" % env

        if what == "diff":
            return FHS.diff_dir / f"{self.hostname}{suffix}.diff"

        if env == "prod":
            base = FHS.prod_dir
        else:
            base = FHS.change_dir

        if what == "catalog":
            ext = ".pson.gz"
        elif what == "errors":
            ext = ".err"
        else:
            raise ValueError("Unrecognized object: %s" % what)
        return base / "catalogs" / f"{self.hostname}{suffix}{ext}"

    def outfile_for(self, env: str, what: str) -> Path:
        """Return the outfile path of a file type in a specific environment

        Argumnets:
            env: The envorinment to search in
            what: The type of file to look for

        Returns:
            Path: The file path to the file

        """
        name = self.file_for(env, what).name
        return self.outdir / f"{env}.{name}"
