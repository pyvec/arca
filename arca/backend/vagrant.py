import json
from pathlib import Path

from git import Repo

from arca.task import Task
from arca.result import Result
from arca.exceptions import ArcaMisconfigured, BuildError
from arca.utils import LazySettingProperty, logger
from .docker import DockerBackend

from vagrant import Vagrant
from fabric import api


@api.task
def run_script(container_name, script_name):
    """ Sequence to run inside the VM, copies data and script to the container and runs the script.
    """
    api.run(f"docker exec {container_name} mkdir -p /srv/scripts")
    api.run(f"docker cp /srv/data {container_name}:/srv")
    api.run(f"docker cp /vagrant/{script_name} {container_name}:/srv/scripts/")
    return api.run(f"docker exec -t {container_name} python /srv/scripts/{script_name}")


class VagrantBackend(DockerBackend):

    box = LazySettingProperty(key="box", default="ubuntu/trusty64")
    provider = LazySettingProperty(key="provider", default="virtualbox")
    quiet = LazySettingProperty(key="quiet", default=False, convert=bool)

    def validate_settings(self):
        super(VagrantBackend, self).validate_settings()

        if self.push_to_registry_name is None:
            raise ArcaMisconfigured("Push to registry setting is required for VagrantBackend")

    def get_vagrant_file_location(self, repo: str, branch: str, git_repo: Repo, repo_path: Path) -> Path:
        """ Returns a directory where Vagrantfile should be. Based on repo, branch and tag of the used docker image.
        """
        path = Path(self._arca.base_dir) / "vagrant"
        path /= self._arca.repo_id(repo)
        path /= branch
        path /= self.get_image_tag(self.get_requirements_file(repo_path), self.get_dependencies())
        return path

    def create_vagrant_file(self, repo: str, branch: str, git_repo: Repo, repo_path: Path):
        """ Creates a Vagrantfile in the target dir with the required settings and the required docker image.
            The image is built locally if not already pushed.
        """
        vagrant_file = self.get_vagrant_file_location(repo, branch, git_repo, repo_path) / "Vagrantfile"

        self.check_docker_access()

        self.get_or_create_environment(repo, branch, git_repo, repo_path)

        requirements_file = self.get_requirements_file(repo_path)
        dependencies = self.get_dependencies()
        image_tag = self.get_image_tag(requirements_file, dependencies)
        image_name = self.push_to_registry_name

        container_name = "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self._arca.current_git_hash(repo, branch, git_repo, short=True)
        )
        workdir = str((Path("/srv/data") / self.cwd))

        vagrant_file.parent.mkdir(exist_ok=True, parents=True)

        vagrant_file.write_text(f"""
# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "{self.box}"
  config.vm.provision "docker" do |d|
    d.pull_images "{image_name}:{image_tag}"
    d.run "{image_name}:{image_tag}",
      name: "{container_name}",
      args: "-t -w {workdir}",
      cmd: "bash -i"
  end

  config.vm.synced_folder "{repo_path}", "/srv/data"
  config.vm.provider "{self.provider}"

end
        """)

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path):
        """ Gets or creates Vagrantfile, starts up a VM with it, executes Fabric script over SSH, returns result.
        """
        vagrant_file = self.get_vagrant_file_location(repo, branch, git_repo, repo_path)

        if not vagrant_file.exists():
            self.create_vagrant_file(repo, branch, git_repo, repo_path)

        script_name, script = self.create_script(task)

        (vagrant_file / script_name).write_text(script)

        container_name = "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self._arca.current_git_hash(repo, branch, git_repo, short=True)
        )

        vagrant = Vagrant(root=vagrant_file, quiet_stdout=self.quiet, quiet_stderr=self.quiet)
        vagrant.up()

        api.env.hosts = [vagrant.user_hostname_port()]
        api.env.key_filename = vagrant.keyfile()
        api.env.disable_known_hosts = True  # useful for when the vagrant box ip changes.
        if self.quiet:
            api.output.everything = False
        else:
            api.output.everything = True

        try:
            res = api.execute(run_script, container_name=container_name, script_name=script_name)

            return Result(json.loads(res[vagrant.user_hostname_port()].stdout))
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e
            })
        finally:
            vagrant.halt()
