"""Classes for managing filsystem objects"""
from pathlib import Path


class FHS:
    """Object to manage the file system hieracry"""

    base_dir = None
    prod_dir = None
    change_dir = None
    diff_dir = None
    output_dir = None

    @classmethod
    def setup(cls, job_id, base):
        """Setup the base file system"""
        base = Path(base)
        cls.base_dir = base / str(job_id)
        cls.prod_dir = cls.base_dir / "production"
        cls.change_dir = cls.base_dir / "change"
        cls.diff_dir = cls.base_dir / "diffs"
        cls.output_dir = base / "output" / str(job_id)


class HostFiles:
    """Class to manage host files"""

    def __init__(self, hostname):
        self.hostname = hostname
        self.outdir = FHS.output_dir / self.hostname

    def file_for(self, env, what):
        """Return the path of a file type in a specific environment"""
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
            ext = ".pson"
        elif what == "errors":
            ext = ".err"
        else:
            raise ValueError("Unrecognized object: %s" % what)
        return base / "catalogs" / f"{self.hostname}{suffix}{ext}"

    def outfile_for(self, env, what):
        """Return the outfile path of a file type in a specific environment"""
        name = self.file_for(env, what).name
        return self.outdir / f"{env}.{name}"
