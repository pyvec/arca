import distutils.cmd


class DeployDockerBasesCommand(distutils.cmd.Command):
    """ A command that builds docker bases for the DockerBackend and deploys them to dockerhub.
    """

    description = "Build and deploy docker bases for the DockerBackend"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from arca import DockerBackend

        backend = DockerBackend()
        backend.check_docker_access()

        base_arca_name, base_arca_tag = backend.get_arca_base(False)

        print(f"Built image {base_arca_name}:{base_arca_tag}")

        if self.verbose:
            for x in backend.client.images.push(base_arca_name, tag=base_arca_tag, stream=True):
                print(x.decode("utf-8"), end="")
        else:
            backend.client.images.push(base_arca_name, tag=base_arca_tag)

        print(f"Pushed image {base_arca_name}:{base_arca_tag}")

        for docker_base in ["3.6.0", "3.6.1", "3.6.2", "3.6.3", "3.6.4"]:  # TODO: dynamically list these
            image_name, image_tag = backend.get_python_base(docker_base, pull=False)

            print(f"Built image {image_name}:{image_tag}")

            if self.verbose:
                for x in backend.client.images.push(image_name, tag=image_tag, stream=True):
                    print(x.decode("utf-8"), end="")
            else:
                backend.client.images.push(image_name, tag=image_tag)

            print(f"Pushed image {image_name}:{image_tag}")
