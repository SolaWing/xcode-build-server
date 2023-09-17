# Xcode-Build-Server

apple's [sourcekit-lsp](https://github.com/apple/sourcekit-lsp) doesn't support xcode project. but I found it provide a [build server protocol](https://build-server-protocol.github.io/docs/specification.html) to integrate with other build system. this is why I created this repo.

This repo aims to integrate xcode with sourcekit-lsp, so I can develop iOS with my favorate editor.

# Install

this repo require Python3.9. it's the default version for newest macos.

clone this repo, and just `ln -s ABSPATH/TO/xcode-build-server /usr/local/bin`

# Usage

choose one of the following usage.

### Bind to Xcode
Go to your workspace directory and execute one of the following commands:

```bash
# *.xcworkspace or *.xcodeproj should be unique. can be omit and will auto choose the unique workspace or project.
xcode-build-server config -scheme <XXX> -workspace *.xcworkspace
xcode-build-server config -scheme <XXX> -project *.xcodeproj
```

This will create or update the `buildServer.json` file, with a `kind: xcode` key, which instructs xcode-build-server to watch and use flags from the newest xcode build log.

If your compile info is outdated and something is not working properly, just build in xcode to refresh it.

### Manual Parse Xcodebuild log

If you are not building with Xcode, you can manually parse the build log to extract compile info using one of the following commands:

```bash
xcode-build-server parse <build_log_file>
<command_to_generate_build_log> | xcode-build-server parse
```

this will parse the log, save compile info in a `.compile` file, and update `buildServer.json` with a `king: manual` key to instruct `xcode-build-server` to use the flags from the `.compile` file.

`<build_log_file>` can be created by redirecting `xcodebuild build` output to a file, or exported from xcode's build log.

`<cmd generate build log>` will usually be xcodebuild, or pbpaste if copy from xcode's build log. for example:

```base
xcodebuild -workspace *.xcworkspace -scheme <XXX> -configuration Debug build | xcode-build-server parse
pbpaste | xcode-build-server parse
```

After completing these steps, restart your language server, and it should work as expected.

if your build environment changes(eg: add new files, switch sdk, toggle debug/release, conditional macro, etc..) and your language server stops working, just repeat the previous steps to update the compile info.

### [Deprecated] Sync Xcodebuild log
> this usage is deprecated by `bind xcodeproj`, which just a command and won't pollute your xcodeproj's config.  
> switch from this usage to `bind xcodeproj`, you'll need to delete the `post-build-action` first. Otherwise, bind may not work properly. since kind will change to manual by post-build-action.

xcode-build-server provider `post-build-action` script to auto parse newest log into .compile and generate `buildServer.json`.  
just add `xcode-build-server postaction | bash &` into script in **scheme -> Build -> Post-actions**. and script should choose provide build settings from target
<img width="918" alt="图片" src="https://user-images.githubusercontent.com/3897953/178139213-cb655340-28f6-49f6-8e7d-666bb29e664f.png">

after this, the compile info should auto generate when xcode build and no need further manual parse.

## Indexing While Building
[sourcekit-lsp](https://github.com/apple/sourcekit-lsp#indexing-while-building) use indexing while build.
if you found find definition or references is not work correctly, just build it to update index

# More

current implementation is basicly work, but may have some rough edges. Please report issue if you have any problem. If you want to help, can check the open issue list. PR is always welcome.
