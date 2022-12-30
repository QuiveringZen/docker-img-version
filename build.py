import os
import subprocess
import re
from typing import Tuple

"""
This script packs an application into docker image, based on Dockerfile and pushes docker image to Dockerhub.
It expects `build.env` file @ repo-root-dir to contain Dockerhub credentials.
It expects `version.txt` file@ repo-root-dir to contain semantic version for docker image tagging purposes.
    - this file is automatically checked and overwriten by the script once new version is build
    - this file contains the current newest version for the image

Args:
    - -t ; pass new version for the image
    - -v ; type of version change, one of ['minor', 'major', 'patch']
Example usage:
    python ./scripts/build.py -t 1.0.2 -v patch
"""


class StaticConfig():
    @staticmethod
    def dockerfile_path() -> str:
        return _get_rel_file_path(
            "../docker/Dockerfile", "dockerfile path")

    @staticmethod
    def build_context() -> str:
        return _get_rel_file_path("../", "project root")

    @staticmethod
    def image_name() -> str:
        return "dock-img"

    @staticmethod
    def semver_file() -> str:
        return _get_rel_file_path("../version.txt", "sem-ver")

    @staticmethod
    def dotenv_file() -> str:
        return _get_rel_file_path("../build.env", "dot-env")


class Dotenv:
    @staticmethod
    def load_dotenv():
        dotenv_path = StaticConfig.dotenv_file()
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=dotenv_path)


class CmdArgs:
    def __init__(self, tag, version):
        self.tag = tag
        self.version = version

    @staticmethod
    def get_cmd_args():
        import argparse
        parser = argparse.ArgumentParser(description="Just an example",
                                         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        parser.add_argument(
            "-t", "--tag", help="tag of the image", required=True)
        parser.add_argument("-v", "--version",
                            help="type of version change", required=True)
        args = parser.parse_args()
        # 2.0.14 2 - major, 0 - minor, 14 - patch
        version_increase_types = ['major', 'minor', 'patch']
        if args.version not in version_increase_types:
            print(
                f'invalid arg value for `version`, available values: {version_increase_types}')
            exit(1)

        return CmdArgs(tag=args.tag, version=args.version)


class SemVersion:
    def __init__(self, raw) -> None:
        self.raw = raw

    def is_valid(self):
        """
        Matches:
        1 - Major
        2 - Minor
        3 - Patch
        4 (optional, not implemented) - Pre-release version info
        5 (optional, not implemented) - Metadata (build time, number, etc.)
        """
        if re.match(
                "^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$", self.raw) is None:
            return False
        return True

    def parse(self) -> Tuple[int, int, int]:
        """
        returns sem-ver in format (minor, major, patch)
        """
        parsed = self.raw.split(".")
        if len(parsed) != 3:
            print("invalid sem-ver format")
            exit(1)
        return (int(parsed[0]), int(parsed[1]), int(parsed[2]))

    @staticmethod
    def validate_semver_change(current_version: __module__, new_version: __module__, args: CmdArgs):
        if current_version.raw == new_version.raw:
            print('current and new sem-versions are matching')
            exit(1)

        (cmaj, cmin, cpatch) = current_version.parse()
        (nmaj, nmin, npatch) = new_version.parse()

        cold = 0
        cnew = 0

        if args.version == 'patch':
            if not (cmaj == nmaj and cmin == cmin):
                print('invalid patch sem-ver change')
                exit(1)
            cold = cpatch
            cnew = npatch
        if args.version == 'minor':
            if not (cmaj == nmaj and npatch == 0):
                print('invalid minor sem-ver change')
                exit(1)
            cold = cmin
            cnew = nmin
        if args.version == 'major':
            if not (cmin == 0 and npatch == 0):
                print('invalid major sem-ver change')
                exit(1)
            cold = cmaj
            cnew = nmaj

        if not (cold + 1 == cnew):
            print(
                f'invalid version increase from `{current_version.raw}` to `{new_version.raw}`')
            exit(1)


class SemVerFile:
    @staticmethod
    def get_current_sem_ver() -> SemVersion:
        path = StaticConfig.semver_file()
        with open(path) as f:
            lines = f.readlines()
            if len(lines) != 1:
                print("invalid version.txt format")
                exit(1)
            version = lines[0]
            return SemVersion(version)

    @staticmethod
    def overwrite_version(new_version: SemVersion):
        if not new_version.is_valid():
            print("invalid sem-ver format")
            exit(1)
        path = StaticConfig.semver_file()
        with open(path, 'w') as f:
            f.write(new_version.raw)


class DockerhubCreds:
    def __init__(self, id, password):
        self.id = id
        self.password = password

    @staticmethod
    def get_dockerhub_creds():
        DOCKERHUB_ID = os.getenv('DOCKERHUB_ID')
        DOCKERHUB_PW = os.getenv('DOCKERHUB_PW')
        if DOCKERHUB_ID is None or DOCKERHUB_PW is None:
            print(f'dockerhub credentials not specified')
            exit(1)
        creds = DockerhubCreds(DOCKERHUB_ID, DOCKERHUB_PW)
        return creds


class Terminal:
    def __del__(self):
        pass

    def login(self, creds: DockerhubCreds) -> None:
        output = subprocess.run(['docker', 'login', '-u', creds.id,
                                 '-p', creds.password], capture_output=True, text=True)
        if output.returncode != 0:
            print('failed to login to dockerhub')
            print(output.stderr)
            exit(1)
        print(output.stdout)

    def build(self, creds: DockerhubCreds, args: CmdArgs) -> None:
        image = _get_full_image_name(creds=creds, args=args)
        output = subprocess.run(['docker', 'build', '-t', image, '-f', StaticConfig.dockerfile_path(),
                                 StaticConfig.build_context()], capture_output=True, text=True)
        if output.returncode != 0:
            print('failed to build image')
            print(output.stderr)
            exit(1)
        print(output.stdout)

    def show_image(self):
        output = subprocess.run(
            ['docker', 'image', 'ls'],  check=True, capture_output=True)
        processNames = subprocess.run(['grep', StaticConfig.image_name()],
                                      input=output.stdout, capture_output=True)
        print(processNames.stdout.decode('utf-8').strip())

    def push(self, creds: DockerhubCreds, args: CmdArgs):
        image = _get_full_image_name(creds=creds, args=args)
        output = subprocess.run(
            ['docker', 'push', image], capture_output=True, text=True)
        if output.returncode != 0:
            print('failed to build image')
            print(output.stderr)
            exit(1)
        print(output.stdout)


def main():
    args: CmdArgs = CmdArgs.get_cmd_args()

    current_version: SemVersion = SemVerFile.get_current_sem_ver()
    if not current_version.is_valid():
        print('invalid version.txt sem-ver specified')
        exit(1)
    new_version: SemVersion = SemVersion(args.tag)
    if not new_version.is_valid():
        print('invalid sem-ver specified as cli -t or --tag argument')
        exit(1)

    SemVersion.validate_semver_change(current_version=current_version,
                                      new_version=new_version, args=args)

    Dotenv.load_dotenv()
    dockerhub_creds: DockerhubCreds = DockerhubCreds.get_dockerhub_creds()

    terminal: Terminal = Terminal()

    print("Start login...")
    terminal.login(creds=dockerhub_creds)

    print("Start build...")
    terminal.build(creds=dockerhub_creds, args=args)

    print("Showing image...")
    terminal.show_image()

    print("Pushing image...")
    terminal.push(creds=dockerhub_creds, args=args)

    SemVerFile.overwrite_version(new_version)


def _get_rel_file_path(rel_path: str, ffor: str) -> str:
    path = os.path.join(os.path.dirname(__file__), rel_path)
    if not os.path.exists(path):
        print(f'for {ffor} not found in path {path} ')
        exit(1)
    return path


def _get_full_image_name(creds: DockerhubCreds, args: CmdArgs):
    """
    Example:
    my_dockerhub_acc/my_backend:1.0.1
    """
    return f'{creds.id}/{StaticConfig.image_name()}:{args.tag}'


if __name__ == "__main__":
    main()
