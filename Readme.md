# Xcode-Build-Server

apple's [sourcekit-lsp](https://github.com/apple/sourcekit-lsp) doesn't support xcode project. but I found it provide a [build server protocol](https://build-server-protocol.github.io/docs/specification.html) to integrate with other build system. this is why I created this repo.

This repo aims to integrate xcode with sourcekit-lsp, so I can develop iOS with my favorate editor.

# Install
clone this repo, and just `ln -s ABSPATH/TO/xcode-build-server /usr/local/bin`

# Usage
**xcode build, copy the build log, and then in Workspace root**, run:

`pbpaste | xcode-build-server parse`

this should generate buildServer.json, which hook sourcekit-lsp to use the buildServer to provide compile infomation
and a .compile hidden file, which provide actual compile command

last, restart your language server, and it should work.

if your build environment changes(eg: add new files, switch sdk, debug/release, conditional macro, etc..) and language server work incorrectly, just repeat previous action to update compile info

PS: Recent Xcode may copy failed. if the case, use the export button to save log to file, and in workspace root run:

`xcode-build-server parse <PATH/TO/Log>`

## Index And Build
[sourcekit-lsp](https://github.com/apple/sourcekit-lsp#indexing-while-building) use indexing while build.
if you found find definition or references is not work correctly, just build it from xcode to update index

# More

current implementation is basicly work, but may have some rough edges. Please report issue if you have any problem. If you want to help, can check the open issue list. PR is always welcome.
