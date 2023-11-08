# Testing

Use the following command to test locally
```
$ CHANGE=731113 NODES=cloudservices1003.wikimedia.org BUILD_NUMBER=1 python3 -m puppet_compiler.cli --debug --force
```
Or to debug a specific host failing
```
$ python3 -m puppet_compiler.debug_host -c 650494 sretest1001.eqiad.wmnet
```
## Steps to create testing environment (Linux)
The following instructions are pretty rough but should enable on to set up an
environment that allows some local hacking.  however please keep in mind that
these instructions don't set up or configure the puppetdb server.  As such you
want be able to test code which makes uses of exported resources or puppetdb
queries

* Create a `puppet-compiler.conf` file and place it in a valid configuration location. In order of precedence, this is:
    * The path specified in the `PC_CONFIG` environment variable
    * The current working directory
    * `XDG_CONFIG_HOME`
    * /etc

A sample configuration file, changing `PATH_TO_REPO` for the full path to the root of the git repository:

```yaml
base: "<PATH_TO_REPO>/.workspace/jenkins-workspace"
puppet_src: "<PATH_TO_REPO>/.workspace/catalog-differ/production"
puppet_private: "<PATH_TO_REPO>/.workspace/catalog-differ/private"
puppet_netbox: "<PATH_TO_REPO>/.workspace/catalog-differ/netbox-hiera"
http_url: "http://localhost"
puppet_var: "<PATH_TO_REPO>/.workspace/catalog-differ/puppet"
store_configs: False
```

* sudo apt-get install ruby-httpclient ruby-ldap ruby-rgen ruby-multi-json puppet
* ./utils/setup_workspace.sh
* ./utils/fetch_facts.sh

## Installing Python dependencies
The puppet compile have a few Python dependencies, which can be installed using:

```
$ python3 -mvenv .venv
$ pip install -r requirements.txt
```

This creates a new virtualenv and installes the required dependencies. Alternatively these can be installed using apt.
You can also use tools like pyenv or Conda rather than virtualenv if that is your preferred way of managing Python dependencies. 

## Running the CI tests locally
You can easily run the same tests that CI is running using the script:
* ./utils/run_ci_locally.sh

## Working with cloud hosts

If you would also like to test cloud hosts then you will need access to the openstack api for both the enc and custom hiera backend.  For this you will need a copy of
    * /usr/local/bin/puppet-enc
    * /etc/puppet-enc.yaml
and also set up a tunnle to the cloud puppetmaster (notice the different port number used to bypass nginx)
    * ssh -N -L8100:localhost:8101 cloud-puppetmaster-03.cloudinfra.eqiad.wmflabs
Finaly add the following to /etc/hosts
    * `127.0.0.1 puppetmaster.cloudinfra.wmflabs.org`

## Testing HTML rendering

The compilation output adds a presentation layer suitable for humans
consumption. You can trigger a dummy rendering to a "tmpdir" directory (which
will be deleted) using:
```
$ python3 -m puppet_compiler.debug_presentation -o tmpdir --force
...
Rendered files:
tmpdir/output/1911/42/srv001.example.org/index.html
tmpdir/output/1911/42/srv001.example.org/fulldiff.html
tmpdir/output/1911/42/srv001.example.org/corediff.html
```

The rendering comes from Jinja2 templates in `./puppet_compiler/templates`.
