# Xcode-Build-Server

apple's [sourcekit-lsp](https://github.com/apple/sourcekit-lsp) doesn't support xcode project. but I found it provide a [build server protocol](https://build-server-protocol.github.io/docs/specification.html) to integrate with other build system. this is why I created this repo.

This repo aims to integrate xcode with sourcekit-lsp, so I can develop iOS with my favorate editor.

# Install
clone this repo, and just `ln -s ABSPATH/TO/xcode-build-server /usr/local/bin`

# Usage
## Manual Parse Xcodebuild log
**xcode build, copy the build log, and then in Workspace root**, run:

`pbpaste | xcode-build-server parse`

this should generate buildServer.json, which hook sourcekit-lsp to use the buildServer to provide compile infomation
and a .compile hidden file, which provide actual compile command

last, restart your language server, and it should work.

if your build environment changes(eg: add new files, switch sdk, debug/release, conditional macro, etc..) and language server work incorrectly, just repeat previous action to update compile info

PS: Recent Xcode may copy failed. if the case, use the export button to save log to file, and in workspace root run:

`xcode-build-server parse <PATH/TO/Log>`

## Sync Xcodebuild log
xcode-build-server provider post-build-action script to auto parse newest log into .compile and generate buildServer.json.  
just add `xcode-build-server postaction | bash &` into script in **scheme -> Build -> Post-actions**. and script should choose provide build settings from target
<img width="918" alt="图片" src="https://user-images.githubusercontent.com/3897953/178139213-cb655340-28f6-49f6-8e7d-666bb29e664f.png">

after this, the compile info should auto generate when xcode build and no need further manual parse.

## Index And Build
[sourcekit-lsp](https://github.com/apple/sourcekit-lsp#indexing-while-building) use indexing while build.
if you found find definition or references is not work correctly, just build it from xcode to update index

# More

current implementation is basicly work, but may have some rough edges. Please report issue if you have any problem. If you want to help, can check the open issue list. PR is always welcome.
