#!/bin/bash -e


setup_repo() {
    local repo_path="${1?No repo_path passed}"
    local repo_url="${2?No repo_url passed}"

    if [[ -e "$repo_path/.git" ]]; then
        reset_git "$repo_path"
    else
        mkdir -p "$repo_path"
        git clone "$repo_url" "$repo_path"
    fi
}


reset_git() {
    local repo_path="${1?No repo_path passed}"
    cd "$repo_path"
    git fetch --all
    git reset --hard FETCH_HEAD
    cd -
}


main() {
    local workspace_path="${1:-.workspace}"
    local prod_puppet_git_path="${workspace_path}/catalog-differ/production"
    local private_git_path="${workspace_path}/catalog-differ/private"
    local netbox_git_path="${workspace_path}/catalog-differ/netbox-hiera"

    mkdir -p "${workspace_path}"/catalog-differ/{production,private,puppet/ssl} "${workspace_path}/jenkins-workspace"

    setup_repo "$prod_puppet_git_path" "https://gerrit.wikimedia.org/r/operations/puppet"
    setup_repo "$private_git_path" "https://gerrit.wikimedia.org/r/labs/private"
    setup_repo "$netbox_git_path" "https://netbox-exports.wikimedia.org/netbox-hiera"

    puppet catalog \
        compile test \
        --vardir  "${workspace_path}/catalog-differ/puppet"

    #puppet cert \
    #    --ssldir  "${workspace_path}/catalog-differ/puppet/ssl" \
    #    --vardir "${workspace_path}/catalog-differ/puppet" \
    #    generate $(hostname -f)
}


main "$@"
