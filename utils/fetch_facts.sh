#!/bin/bash -e
REMOTE_TMP_PATH=/tmp/puppet-facts-export.tar.xz
LOCAL_TMP_PATH=/tmp/puppet-facts-export.tar.xz
LOCAL_DST_PATH=.workspace/catalog-differ/puppet


help() {
    cat <<EOH
    Usage: $0 [-h|-s] [PUPPETMASTER]

    Options:
        -h Show this help
        -s Skip exporting the facts, this expects the facts to exist already in the remote ${REMOTE_TMP_PATH}

    Arguments:
        PUPPETMASTER name of the puppetmaster that will fetch the facts out of
            (ex. puppetmaster1001.eqiad.wmnet or cloud-puppetmaster-05.cloudinfra.eqiad1.wikimedia.cloud)
EOH
}

main() {
    local export_facts="true"
    if [[ "$1" == "-h" ]]; then
        help
        exit
    fi
    if [[ "$1" == "-s" ]]; then
        export_facts="false"
        shift
    fi

    local puppetmaster="${1:-puppetmaster1001.eqiad.wmnet}"
    if [[ "$export_facts" == "false" ]]; then
        echo "Skipping exporting the facts, -s passed."
    else
        echo "Exporting the facts from ${puppetmaster}, might take a few seconds..."
        ssh "${puppetmaster}" sudo /usr/local/bin/puppet-facts-export
    fi

    echo "Copying locally to ${LOCAL_TMP_PATH}"
    scp "${puppetmaster}:${REMOTE_TMP_PATH}" "${LOCAL_TMP_PATH}"
    echo "Extracting..."
    rm -rf "${LOCAL_DST_PATH}/yaml"
    mkdir -p "${LOCAL_DST_PATH}"
    tar xvf "${LOCAL_TMP_PATH}" --directory "${LOCAL_DST_PATH}"
    echo "Cleaning up ${REMOTE_TMP_PATH}"
    ssh "${puppetmaster}" sudo rm "${REMOTE_TMP_PATH}"
    echo "Done!"
}


main "$@"
