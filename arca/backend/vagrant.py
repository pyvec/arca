import json
import re
import subprocess
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from fabric import api
from git import Repo

from arca.exceptions import ArcaMisconfigured, BuildError
from arca.result import Result
from arca.task import Task
from arca.utils import LazySettingProperty, logger
from .docker import DockerBackend


@api.task
def run_script(container_name, script_name):
    """ Sequence to run inside the VM, copies data and script to the container and runs the script.
    """
    api.run(f"docker exec {container_name} mkdir -p /srv/scripts")
    api.run(f"docker cp /srv/data {container_name}:/srv")
    api.run(f"docker cp /vagrant/{script_name} {container_name}:/srv/scripts/")
    return api.run(f"docker exec -t {container_name} python /srv/scripts/{script_name}")


class VagrantBackend(DockerBackend):
    """ Uses Docker in Vagrant.

    Inherits settings from :class:`DockerBackend`:

    * **python_version**
    * **apk_dependencies**
    * **disable_pull**
    * **inherit_image**
    * **push_to_registry_name**

    Adds new settings:

    * **box** - what Vagrant box to use (must include docker >= 1.8 or no docker)
    * **provider** - what provider should Vagrant user
    * **quiet** - Keeps the extra vagrant logs quiet.
    * **destroy** - Destroy or just halt the VMs (default is ``True``)

    """

    # Box has to either not contain docker at all (will be installed in that case, takes a long time)
    # or has to contain Docker with version >= 1.8 (Versions < 1.8 can't copy files from host to container)
    box = LazySettingProperty(key="box", default="ailispaw/barge")
    provider = LazySettingProperty(key="provider", default="virtualbox")
    quiet = LazySettingProperty(key="quiet", default=True, convert=bool)
    destroy = LazySettingProperty(key="destroy", default=True, convert=bool)

    def validate_settings(self):
        """ Runs :meth:`arca.DockerBackend.validate_settings` and checks extra:

        * ``box`` format
        * ``provider`` format
        * ``push_to_registry_name`` is set
        """
        super(VagrantBackend, self).validate_settings()

        if self.push_to_registry_name is None:
            raise ArcaMisconfigured("Push to registry setting is required for VagrantBackend")

        if not re.match(r"^[a-z]+/[a-zA-Z0-9\-_]+$", self.box):
            raise ArcaMisconfigured("Provided Vagrant box is not valid")

        if not re.match(r"^[a-z_]+$", self.provider):
            raise ArcaMisconfigured("Provided Vagrant provider is not valid")

    def check_vagrant_access(self):
        """
        :raise BuildError: If Vagrant is not installed.
        """
        from vagrant import get_vagrant_executable

        if get_vagrant_executable() is None:
            raise BuildError("Vagrant executable is not accessible!")

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

        self.get_image_for_repo(repo, branch, git_repo, repo_path)

        requirements_file = self.get_requirements_file(repo_path)
        dependencies = self.get_dependencies()
        image_tag = self.get_image_tag(requirements_file, dependencies)
        image_name = self.push_to_registry_name

        logger.info("Creating Vagrantfile with image %s:%s", image_name, image_tag)

        container_name = "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self._arca.current_git_hash(repo, branch, git_repo, short=True)
        )
        workdir = str((Path("/srv/data") / self.cwd))

        vagrant_file.parent.mkdir(exist_ok=True, parents=True)

        vagrant_file.write_text(dedent(f"""
        # -*- mode: ruby -*-
        # vi: set ft=ruby :

        Vagrant.configure("2") do |config|
          config.vm.box = "{self.box}"
          config.ssh.insert_key = true
          config.vm.provision "docker" do |d|
            d.pull_images "{image_name}:{image_tag}"
            d.run "{image_name}:{image_tag}",
              name: "{container_name}",
              args: "-t -w {workdir}",
              cmd: "bash -i"
          end

          config.vm.synced_folder ".", "/vagrant"
          config.vm.synced_folder "{repo_path}", "/srv/data"
          config.vm.provider "{self.provider}"

        end
        """))

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path):
        """ Gets or creates Vagrantfile, starts up a VM with it, executes Fabric script over SSH, returns result.
        """
        # importing here, prints out warning when vagrant is missing even when the backend is not used otherwise
        from vagrant import Vagrant, make_file_cm

        self.check_vagrant_access()

        vagrant_file = self.get_vagrant_file_location(repo, branch, git_repo, repo_path)

        if not vagrant_file.exists():
            logger.info("Vagrantfile doesn't exist, creating")
            self.create_vagrant_file(repo, branch, git_repo, repo_path)

        logger.info("Vagrantfile in folder %s", vagrant_file)

        script_name, script = self.create_script(task)

        (vagrant_file / script_name).write_text(script)

        container_name = "arca_{}_{}_{}".format(
            self._arca.repo_id(repo),
            branch,
            self._arca.current_git_hash(repo, branch, git_repo, short=True)
        )

        log_path = Path(self._arca.base_dir) / "logs" / (str(uuid4()) + ".log")
        log_path.parent.mkdir(exist_ok=True, parents=True)
        log_cm = make_file_cm(log_path)
        logger.info("Storing vagrant log in %s", log_path)

        vagrant = Vagrant(root=vagrant_file, quiet_stdout=self.quiet, quiet_stderr=self.quiet,
                          out_cm=log_cm, err_cm=log_cm)
        try:
            vagrant.up()
        except subprocess.CalledProcessError:
            raise BuildError("Vagrant VM couldn't up launched. See output for details.")

        api.env.hosts = [vagrant.user_hostname_port()]
        api.env.key_filename = vagrant.keyfile()
        api.env.disable_known_hosts = True  # useful for when the vagrant box ip changes.
        api.env.abort_exception = BuildError  # raises SystemExit otherwise
        api.env.shell = "/bin/sh -l -c"
        if self.quiet:
            api.output.everything = False
        else:
            api.output.everything = True

        try:
            res = api.execute(run_script, container_name=container_name, script_name=script_name)

            return Result(json.loads(res[vagrant.user_hostname_port()].stdout))
        except BuildError:  # can be raised by  :meth:`Result.__init__`
            raise
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e
            })
        finally:
            if self.destroy:
                vagrant.destroy()
            else:
                vagrant.halt()
