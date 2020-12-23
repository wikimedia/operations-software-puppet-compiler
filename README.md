# Testing

Use the following command to test localy
```
$ CHANGE=588086 NODES=mwlog2001.codfw.wmnet BUILD_NUMBER=1  python3 -m puppet_compiler.cli  --debug
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

* create a /etc/puppet-compiler.conf file with the following
```yaml
base: "/srv/jenkins-workspace/puppet-compiler"
puppet_src: "/var/lib/catalog-differ/production"
puppet_private: "/var/lib/catalog-differ/private"
http_url: "http://localhost"
puppet_var: "/var/lib/catalog-differ/puppet"
```
* sudo apt-get install python3-jinja2 python3-yaml python3-requests ruby-httpclient ruby-ldap ruby-rgen ruby-multi-json
* sudo mkdir -p /var/lib/catalog-differ/{production,private,puppet} /srv/jenkins-workspace/puppet-compiler
* sudo chown ${USER} -R /var/lib/catalog-differ /srv/jenkins-workspace/puppet-compiler
* git clone "https://gerrit.wikimedia.org/r/operations/puppet" /var/lib/catalog-differ/production
* git clone "https://gerrit.wikimedia.org/r/labs/private" /var/lib/catalog-differ/private
* /usr/bin/puppet master --compile test --vardir  /var/lib/catalog-differ/puppet
* /usr/bin/puppet cert --ssldir  /var/lib/catalog-differ/puppet/ssl --vardir /var/lib/catalog-differ/puppet generate $(hostname -f)
* ssh puppetmaster1001.eqiad.wmnet sudo /usr/local/bin/puppet-facts-export
* scp puppetmaster1001.eqiad.wmnet:/tmp/puppet-facts-export.tar.xz /tmp
* tar xvf /tmp/puppet-facts-export.tar.xz --directory /var/lib/catalog-differ/puppet/ 
* ssh puppetmaster1001.eqiad.wmnet sudo rm /tmp/puppet-facts-export.tar.xz 

