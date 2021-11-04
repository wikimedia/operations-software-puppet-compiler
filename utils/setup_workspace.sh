#!/bin/bash -e


main() {
    local workspace_path="${1:-.workspace}"
    mkdir -p "${workspace_path}"/catalog-differ/{production,private,puppet/ssl} "${workspace_path}/jenkins-workspace"
    git clone "https://gerrit.wikimedia.org/r/operations/puppet" "${workspace_path}/catalog-differ/production"
    git clone "https://gerrit.wikimedia.org/r/labs/private" "${workspace_path}/catalog-differ/private"
    puppet master \
        --compile test \
        --vardir  "${workspace_path}/catalog-differ/puppet"
    puppet cert \
        --ssldir  "${workspace_path}/catalog-differ/puppet/ssl" \
        --vardir "${workspace_path}/catalog-differ/puppet" \
        generate $(hostname -f)
}


main "$@"
