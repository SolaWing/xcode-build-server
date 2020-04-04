# Xcode-Build-Server
a [build server protocol](https://build-server-protocol.github.io/docs/specification.html) implement for provide xcode compile infomation to [sourcekit-lsp](https://github.com/apple/sourcekit-lsp)

# Install
clone this repo, and just `ln -s ABSPATH/TO/xcode-build-server /usr/local/bin`

# Usage
In Workspace root, run `xcode-build-server config` to generate buildServer.json. so sourcekit-lsp will use xcode-build-server to provide compile infomation.

Then, xcode build, copy the build log, and run `pbpaste | xcode-build-server parse -o .compile` to put formatted compile log into the module root dir.

Then, the lsp should get the flags from .compile file(which should be in ancestor dir of the swift file)

# TODO
- [] auto recognize xcode project and extract compile infomation from it.
- [] scan workspace and provide targets information
