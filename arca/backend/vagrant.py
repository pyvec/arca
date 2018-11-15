import math
import re
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from git import Repo

from arca.exceptions import ArcaMisconfigured, BuildError, BuildTimeoutError
from arca.result import Result
from arca.task import Task
from arca.utils import LazySettingProperty, logger
from .docker import DockerBackend


class VagrantBackend(DockerBackend):
    """ Uses Docker in Vagrant.

    Inherits settings from :class:`DockerBackend`:

    * **python_version**
    * **apt_dependencies**
    * **disable_pull**
    * **inherit_image**
    * **use_registry_name**
    * **keep_containers_running** - applies for containers inside the VM, default being ``True`` for this backend

    Adds new settings:

    * **box** - what Vagrant box to use (must include docker >= 1.8 or no docker), ``ailispaw/barge`` being the default
    * **provider** - what provider should Vagrant user, ``virtualbox`` being the default
    * **quiet** - Keeps the extra vagrant logs quiet, ``True`` being the default
    * **keep_vm_running** - Keeps the VM up until :meth:`stop_vm` is called, ``False`` being the default
    * **destroy** - Destroy the VM (instead of halt) when stopping it, ``False`` being the default

    """

    # Box has to either not contain docker at all (will be installed in that case, takes a long time)
    # or has to contain Docker with version >= 1.8 (Versions < 1.8 can't copy files from host to container)
    box = LazySettingProperty(default="ailispaw/barge")
    provider = LazySettingProperty(default="virtualbox")
    quiet = LazySettingProperty(default=True, convert=bool)
    keep_container_running = LazySettingProperty(default=True, convert=bool)
    keep_vm_running = LazySettingProperty(default=False, convert=bool)
    destroy = LazySettingProperty(default=False, convert=bool)

    def __init__(self, **kwargs):
        """ Initializes the instance and checks that docker and vagrant are installed.
        """
        super().__init__(**kwargs)

        try:
            import docker  # noqa: F401
        except ImportError:
            raise ArcaMisconfigured(ArcaMisconfigured.PACKAGE_MISSING.format("docker"))

        try:
            import vagrant
        except ImportError:
            raise ArcaMisconfigured(ArcaMisconfigured.PACKAGE_MISSING.format("python-vagrant"))

        try:
            import fabric  # noqa: F401
        except ImportError:
            raise ArcaMisconfigured(ArcaMisconfigured.PACKAGE_MISSING.format("fabric3"))

        if vagrant.get_vagrant_executable() is None:
            raise ArcaMisconfigured("Vagrant executable is not accessible!")

        self.vagrant: vagrant.Vagrant = None

    def inject_arca(self, arca):
        """ Apart from the usual validation stuff it also creates log file for this instance.
        """
        super().inject_arca(arca)

        import vagrant

        self.log_path = Path(self._arca.base_dir) / "logs" / (str(uuid4()) + ".log")
        self.log_path.parent.mkdir(exist_ok=True, parents=True)
        logger.info("Storing vagrant log in %s", self.log_path)

        self.log_cm = vagrant.make_file_cm(self.log_path)

    def validate_configuration(self):
        """ Runs :meth:`arca.DockerBackend.validate_configuration` and checks extra:

        * ``box`` format
        * ``provider`` format
        * ``use_registry_name`` is set and ``registry_pull_only`` is not enabled.
        """
        super().validate_configuration()

        if self.use_registry_name is None:
            raise ArcaMisconfigured("Use registry name setting is required for VagrantBackend")

        if not re.match(r"^[a-z]+/[a-zA-Z0-9\-_]+$", self.box):
            raise ArcaMisconfigured("Provided Vagrant box is not valid")

        if not re.match(r"^[a-z_]+$", self.provider):
            raise ArcaMisconfigured("Provided Vagrant provider is not valid")

        if self.registry_pull_only:
            raise ArcaMisconfigured("Push must be enabled for VagrantBackend")

    def get_vm_location(self) -> Path:
        """ Returns a directory where a Vagrantfile should be - folder called ``vagrant`` in the Arca base dir.
        """
        return Path(self._arca.base_dir) / "vagrant"

    def init_vagrant(self, vagrant_file):
        """ Creates a Vagrantfile in the target dir, with only the base image pulled.
            Copies the runner script to the directory so it's accessible from the VM.
        """
        if self.inherit_image:
            image_name, image_tag = str(self.inherit_image).split(":")
        else:
            image_name = self.get_arca_base_name()
            image_tag = self.get_python_base_tag(self.get_python_version())

        logger.info("Creating Vagrantfile located in %s, base image %s:%s", vagrant_file, image_name, image_tag)

        repos_dir = (Path(self._arca.base_dir) / 'repos').resolve()
        vagrant_file.parent.mkdir(exist_ok=True, parents=True)
        vagrant_file.write_text(dedent(f"""
        # -*- mode: ruby -*-
        # vi: set ft=ruby :

        Vagrant.configure("2") do |config|
          config.vm.box = "{self.box}"
          config.ssh.insert_key = true
          config.vm.provision "docker" do |d|
            d.pull_images "{image_name}:{image_tag}"
          end

          config.vm.synced_folder ".", "/vagrant"
          config.vm.synced_folder "{repos_dir}", "/srv/repos"
          config.vm.provider "{self.provider}"

        end
        """))

        (vagrant_file.parent / "runner.py").write_text(self.RUNNER.read_text())

    @property
    def fabric_task(self):
        """ Returns a fabric task which executes the script in the Vagrant VM
        """
        from fabric import api

        @api.task
        def run_script(container_name, definition_filename, image_name, image_tag, repository, timeout):
            """ Sequence to run inside the VM.
                Starts up the container if the container is not running
                (and copies over the data and the runner script)
                Then the definition is copied over and the script launched.
                If the VM is gonna be shut down then kills the container as well.
            """
            workdir = str((Path("/srv/data") / self.cwd).resolve())
            cmd = "sh" if self.inherit_image else "bash"

            api.run(f"docker pull {image_name}:{image_tag}")

            container_running = int(api.run(f"docker ps --format '{{.Names}}' -f name={container_name} | wc -l"))
            container_stopped = int(api.run(f"docker ps -a --format '{{.Names}}' -f name={container_name} | wc -l"))

            if container_running == 0:
                if container_stopped:
                    api.run(f"docker rm -f {container_name}")

                api.run(f"docker run "
                        f"--name {container_name} "
                        f"--workdir \"{workdir}\" "
                        f"-dt {image_name}:{image_tag} "
                        f"{cmd} -i")

                api.run(f"docker exec {container_name} mkdir -p /srv/scripts")
                api.run(f"docker cp /srv/repos/{repository} {container_name}:/srv/branch")
                api.run(f"docker exec --user root {container_name} bash -c 'mv /srv/branch/* /srv/data'")
                api.run(f"docker exec --user root {container_name} rm -rf /srv/branch")
                api.run(f"docker cp /vagrant/runner.py {container_name}:/srv/scripts/")

            api.run(f"docker cp /vagrant/{definition_filename} {container_name}:/srv/scripts/")

            output = api.run(
                " ".join([
                    "docker", "exec", container_name,
                    "python", "/srv/scripts/runner.py", f"/srv/scripts/{definition_filename}",
                ]),
                timeout=math.ceil(timeout)
            )

            if not self.keep_container_running:
                api.run(f"docker kill {container_name}")

            return output

        return run_script

    def ensure_vm_running(self, vm_location):
        """ Gets or creates a Vagrantfile in ``vm_location`` and calls ``vagrant up`` if the VM is not running.
        """
        import vagrant

        if self.vagrant is None:
            vagrant_file = vm_location / "Vagrantfile"
            if not vagrant_file.exists():
                self.init_vagrant(vagrant_file)

            self.vagrant = vagrant.Vagrant(vm_location,
                                           quiet_stdout=self.quiet,
                                           quiet_stderr=self.quiet,
                                           out_cm=self.log_cm,
                                           err_cm=self.log_cm)

        status = [x for x in self.vagrant.status() if x.name == "default"][0]

        if status.state != "running":
            try:
                self.vagrant.up()
            except subprocess.CalledProcessError:
                raise BuildError("Vagrant VM couldn't up launched. See output for details.")

    def run(self, repo: str, branch: str, task: Task, git_repo: Repo, repo_path: Path):
        """ Starts up a VM, builds an docker image and gets it to the VM, runs the script over SSH, returns result.
            Stops the VM if ``keep_vm_running`` is not set.
        """
        from fabric import api
        from fabric.exceptions import CommandTimeout

        # start up or get running VM
        vm_location = self.get_vm_location()
        self.ensure_vm_running(vm_location)
        logger.info("Running with VM located at %s", vm_location)

        # pushes the image to the registry so it can be pulled in the VM
        self.check_docker_access()  # init client
        self.get_image_for_repo(repo, branch, git_repo, repo_path)

        requirements_option, requirements_hash = self.get_requirements_information(repo_path)

        # getting things needed for execution over SSH
        image_tag = self.get_image_tag(requirements_option, requirements_hash, self.get_dependencies())
        image_name = self.use_registry_name

        task_filename, task_json = self.serialized_task(task)
        (vm_location / task_filename).write_text(task_json)

        container_name = self.get_container_name(repo, branch, git_repo)

        # setting up Fabric
        api.env.hosts = [self.vagrant.user_hostname_port()]
        api.env.key_filename = self.vagrant.keyfile()
        api.env.disable_known_hosts = True  # useful for when the vagrant box ip changes.
        api.env.abort_exception = BuildError  # raises SystemExit otherwise
        api.env.shell = "/bin/sh -l -c"
        if self.quiet:
            api.output.everything = False
        else:
            api.output.everything = True

        # executes the task
        try:
            res = api.execute(self.fabric_task,
                              container_name=container_name,
                              definition_filename=task_filename,
                              image_name=image_name,
                              image_tag=image_tag,
                              repository=str(repo_path.relative_to(Path(self._arca.base_dir).resolve() / 'repos')),
                              timeout=task.timeout)

            return Result(res[self.vagrant.user_hostname_port()].stdout)
        except CommandTimeout:
            raise BuildTimeoutError(f"The task timeouted after {task.timeout} seconds.")
        except BuildError:  # can be raised by  :meth:`Result.__init__`
            raise
        except Exception as e:
            logger.exception(e)
            raise BuildError("The build failed", extra_info={
                "exception": e
            })
        finally:
            # stops or destroys the VM if it should not be kept running
            if not self.keep_vm_running:
                if self.destroy:
                    self.vagrant.destroy()
                    shutil.rmtree(self.vagrant.root, ignore_errors=True)
                    self.vagrant = None
                else:
                    self.vagrant.halt()

    def stop_containers(self):
        """ Raises an exception in this backend, can't be used. Stop the entire VM instead.
        """
        raise ValueError("Can't be used here, stop the entire VM instead.")

    def stop_vm(self):
        """ Stops or destroys the VM used to launch tasks.
        """
        if self.vagrant is not None:
            if self.destroy:
                self.vagrant.destroy()
                shutil.rmtree(self.vagrant.root, ignore_errors=True)
                self.vagrant = None
            else:
                self.vagrant.halt()
