# Xcode-Build-Server

apple's [sourcekit-lsp](https://github.com/apple/sourcekit-lsp) doesn't support xcode project. but I found it provide a [build server protocol](https://build-server-protocol.github.io/docs/specification.html) to integrate with other build system. this is why I created this repo.

This repo aims to integrate xcode with sourcekit-lsp, support all languages(swift, c, cpp, objc, objcpp) xcode supports, so I can develop iOS with my favorate editor.

# Install

this repo require Python3.9. The latest macos already contains this tool.

then just clone this repo, and `ln -s ABSPATH/TO/xcode-build-server /usr/local/bin`

here is script for quick install if your terminal cd to the dir you what save this repo:

`git clone "git@github.com:SolaWing/xcode-build-server.git" && ln -s "$PWD"/xcode-build-server/xcode-build-server /usr/local/bin`

or

`git clone "https://github.com/SolaWing/xcode-build-server.git" && ln -s "$PWD"/xcode-build-server/xcode-build-server /usr/local/bin`

or install from brew

`brew install xcode-build-server`

or install from [Macports](https://github.com/macports/macports-ports/blob/master/devel/xcode-build-server/Portfile):

`sudo port install xcode-build-server`

# Usage

choose one of the following usage. No matter which method you use, you need to ensure that the directory where `buildServer.json` is located is **the root directory** of lsp

### Bind to Xcode
Go to your workspace directory and execute one of the following commands:

```bash
# *.xcworkspace or *.xcodeproj should be unique. can be omit and will auto choose the unique workspace or project.
xcode-build-server config -workspace *.xcworkspace -scheme <XXX> 
xcode-build-server config -project *.xcodeproj -scheme <XXX> 
```

This will create or update the `buildServer.json` file, with a `kind: xcode` key, which instructs xcode-build-server to watch and use compile flags from the newest xcode build log.

After this, you can open your file with sourcekit-lsp enabled, and it should works.

If your compile info is outdated and something is not working properly, just build in xcode to refresh compile flags.

> PS: xcodebuild can generate same build log as xcode, if you don't overwrite build dir and specify a -resultBundlePath. this way you don't have to open xcode to build. eg:
```bash
rm .bundle; xcodebuild -workspace *.xcworkspace -scheme <XXX> -destination 'generic/platform=iOS Simulator' -resultBundlePath .bundle build
```

### Manual Parse Xcodebuild log

If you are not building with Xcode, you can manually parse the build log to extract compile info using one of the following commands:

```bash
xcode-build-server parse [-a] <build_log_file>
<command_to_generate_build_log> | xcode-build-server parse [-a]
```

this will parse the log, save compile info in a `.compile` file, and update `buildServer.json` with a `kind: manual` key to instruct `xcode-build-server` to use the flags from the `.compile` file.


`<build_log_file>` can be created by redirecting `xcodebuild build` output to a file, or exported from xcode's build log UI.

`<cmd generate build log>` will usually be xcodebuild, or `pbpaste` if copy from xcode's build log. for example:

```base
xcodebuild -workspace *.xcworkspace -scheme <XXX> -configuration Debug build | xcode-build-server parse [-a]

pbpaste | xcode-build-server parse [-a]
```

When running for the first time, **you need to ensure that the log is complete**, otherwise some files cannot obtain the correct flags.

After completing these steps, restart your language server, and it should work as expected.

if your build environment changes(eg: add new files, switch sdk, toggle debug/release, conditional macro, etc..) and your language server stops working, just repeat the previous steps to update the compile info. In these incremental update cases, **you should make sure to use the `-a` flag**, which will only add new flags, and other irrelevant old flags will remain unchanged.

if you use xcodebuild and want to see raw output, currently you can use the following commands: `xcodebuild ... | tee build.log; xcode-build-server parse -a build.log >/dev/null 2>&1`

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

# Common Issues

* If you use multiple versions of xcode or sourcekit-lsp, and it doesn't work properly, such as Loading the standard library failed, you should check that the build and sourcekit-lsp versions are **consistent**. Usually you can use `xcode-select` to switch toolchains, and use `xcrun sourcekit-lsp` to use the corresponding lsp version.
* If cross-file references don't work for you, the "build_root" property might not be configured correctly in `buildServer.json`. It should look like `"build_root": "/Users/yourusername/Library/Developer/Xcode/DerivedData/Simulator_Controller-adadrfjxhdizubdktugddworgvuj"` rather than `"build_root":  "/Users/yourusername"`. Fix this by running `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` in the root of your XCode project. For more details, see [this issue](https://github.com/SolaWing/xcode-build-server/issues/55).

# Development

## Release new version
1. Create a new tag with `git tag -a v0.1.0 -m "release 0.1.0"`
2. Push tag with `git push origin v0.1.0`
3. GitHub action will create release
