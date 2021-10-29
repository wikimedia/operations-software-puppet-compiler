# Testing

Use the following command to test localy
```
$ CHANGE=731113 NODES=cloudservices1003.wikimedia.org BUILD_NUMBER=1 PC_CONFIG=~/.config/puppet-compiler.conf python3 -m puppet_compiler.cli  --debug --force
```
Or to debug a specific host failing
```
$ python3 -m puppet_compiler.debug_host -c 650494 sretest1001.eqiad.wmnet
```
## Steps to create testing environment (Linux)
The following instructions are pretty rough but should enable on to set up an
environment that allows some local hacking.  however please keep in mind that
theses instructions dont set up or configure the puppetdb server.  As such you
want be able to test code which makes uses of exported resources or puppetdb
queries

* create a $HOME/.config/puppet-compiler.conf file with the following
```yaml
base: "<PATH_TO_REPO>/.workspace/jenkins-workspace"
puppet_src: "<PATH_TO_REPO>/.workspace/catalog-differ/production"
puppet_private: "<PATH_TO_REPO>/.workspace/catalog-differ/private"
http_url: "http://localhost"
puppet_var: "<PATH_TO_REPO>/.workspace/catalog-differ/puppet"
```

Changing `PATH_TO_REPO` for the full path to the root of the gite repository.

* sudo apt-get install ruby-httpclient ruby-ldap ruby-rgen ruby-multi-json puppet
* ./utils/setup_workspace.sh
* ./utils/fetch_facts.sh


## Running the CI tests locally
You can easily run the same tests that CI is running using the script:
* ./utils/run_ci_locally.sh
