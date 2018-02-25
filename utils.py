import distutils.cmd
import re
from pathlib import Path


class DeployDockerBasesCommand(distutils.cmd.Command):
    """ A command that builds docker bases for the DockerBackend and deploys them to dockerhub.
    """

    description = "Build and deploy docker bases for the DockerBackend"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def list_python_versions(self):
        from arca import Arca
        arca = Arca()

        _, pyenv = arca.get_files("https://github.com/pyenv/pyenv.git", "master")

        build_for = re.compile(r"^3\.[67]\.[0-9]+$")

        for path in sorted((pyenv / "plugins/python-build/share/python-build/").iterdir()):  # type: Path
            if path.is_dir():
                continue

            if build_for.match(path.name):
                yield path.name

    def run(self):
        import requests
        import arca
        from arca import DockerBackend

        backend = DockerBackend()
        backend.check_docker_access()

        response = requests.get(
            "https://hub.docker.com/v2/repositories/mikicz/arca/tags/",
            params={"page_size": 1000}
        )
        response = response.json()
        available_tags = [x["name"] for x in response["results"]]

        if arca.__version__ in available_tags:
            print("This version was already pushed into the registry.")
            base_arca_name, base_arca_tag = backend.get_arca_base()
            print(f"Pulled image {base_arca_name}:{base_arca_tag}, might have to build new python versions.")
        else:
            base_arca_name, base_arca_tag = backend.get_arca_base(pull=False)
            print(f"Built image {base_arca_name}:{base_arca_tag}")

            if self.verbose:
                for x in backend.client.images.push(base_arca_name, tag=base_arca_tag, stream=True):
                    print(x.decode("utf-8"), end="")
            else:
                backend.client.images.push(base_arca_name, tag=base_arca_tag)

            print(f"Pushed image {base_arca_name}:{base_arca_tag}")

        for python_version in self.list_python_versions():
            tag = backend.get_python_base_tag(python_version)
            if tag in available_tags:
                print(f"Skipping Python version {python_version}, already built for this version of arca.")
                continue

            image_name, image_tag = backend.get_python_base(python_version, pull=False)

            print(f"Built image {image_name}:{image_tag}")

            if self.verbose:
                for x in backend.client.images.push(image_name, tag=image_tag, stream=True):
                    print(x.decode("utf-8"), end="")
            else:
                backend.client.images.push(image_name, tag=image_tag)

            print(f"Pushed image {image_name}:{image_tag}")
