#!/usr/bin/env bash

# need the following min environment to run this script
# WORKSPACE_PATH
# SCHEME_NAME
if [[ -n $SCHEME_ACTION_NAME ]]; then
    currentSeconds=$(date +%s)
else
    currentSeconds=0 # not wait newer script generate
fi

# exec &>/tmp/a.log
if [[ -z $WORKSPACE_PATH ]]; then
    echo "you should run this script in xcode post build action or provide WORKSPACE_PATH and SCHEME_NAME environment"
    exit 2
fi

if [[ -z $SRCROOT ]]; then
    if [[ $WORKSPACE_PATH == *xcodeproj/project.xcworkspace ]]; then
        cd "$WORKSPACE_PATH"/../..
    else
        cd "$WORKSPACE_PATH"/..
    fi
    SRCROOT=$(pwd)
else
    cd "$SRCROOT"
fi
if [[ -n $INDEX_DATA_STORE_DIR ]]; then
    ROOT="$INDEX_DATA_STORE_DIR"/../..
else
    ROOT=$(xcodebuild -showBuildSettings -workspace "$WORKSPACE_PATH" -scheme "$SCHEME_NAME" 2>/dev/null | grep "\bBUILD_DIR =" | head -1 | awk '{print $3}' | tr -d '"')/../..
fi
GeneratePath="buildServer.json"
if (( currentSeconds != 0 )); then
    # xcode may delay generate log file, wait it for a while
    ManifestPath="$ROOT"/Logs/Build/LogStoreManifest.plist
    function validElapsedTime() {
        lastModificationSeconds=$(date -r "$ManifestPath" "+%s")
        (( lastModificationSeconds > currentSeconds - 60 ))
    }
    for (( i = 0; i < 10; i++ )); do
        if [[ $ManifestPath -nt $GeneratePath ]] && validElapsedTime; then
            break
        fi
        sleep 1
    done
    if (( i == 10 )); then
        echo "no newer $ManifestPath generate in 10 seconds, abort"
        exit 3
    fi
fi
echo pwd: $(pwd)
xcode-build-server parse -as "$ROOT"
touch "$GeneratePath"
