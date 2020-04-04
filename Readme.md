# Xcode-Build-Server

apple's [sourcekit-lsp](https://github.com/apple/sourcekit-lsp) doesn't support xcode project. but I found it provide a [build server protocol](https://build-server-protocol.github.io/docs/specification.html) to integrate with other build system. this is why I created this repo.

This repo aims to integrate xcode with sourcekit-lsp, so I can develop iOS with my favorate editor.

# Install
clone this repo, and just `ln -s ABSPATH/TO/xcode-build-server /usr/local/bin`

# Usage
In Workspace root, run `xcode-build-server config` to generate buildServer.json. so sourcekit-lsp will use xcode-build-server to provide compile infomation.

Then, xcode build, copy the build log, and run `pbpaste | xcode-build-server parse -o .compile` to put formatted compile log into the module root dir.

Then, the lsp should get the flags from .compile file(which should be in ancestor dir of the swift file)

# TODO

current implementation is basicly work, but may have some rough edges. Please report issue if you have any problem. PR is also welcome.

- [ ] auto recognize xcode project and extract compile infomation from it.
- [ ] scan workspace and provide targets information
- [ ] observe changes and notify lsp
- [ ] refactor to swift, make it more frendly for swifter
