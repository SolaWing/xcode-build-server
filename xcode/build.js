#!/usr/bin/env osascript -l JavaScript

// this need xcode call authorized
function run(argv) {
  if (argv.length < 1 || argv[0] == "-h" || argv[0] == "--help") {
    console.log([
      `Usage: osascript -l JavaScript build.js <path_to_workspace> [scheme]`,
      "",
      "path_to_workspace, scheme can use . as current"
    ].join("\n"))
    return;
  }
  var xcode = Application("Xcode");
  var path = argv[0];
  if (path == ".") {
    console.log("get active workspace")
    var workspace = xcode.activeWorkspaceDocument();
    if (!workspace) {
      console.log("no active workspace, choose one with path or in xcode")
    }
  } else {
    console.log(`open workspace ${path}`)
    var pathURL = $.NSURL.fileURLWithPath(path);
    var workspace = xcode.open(pathURL.path.UTF8String);

    // ctrl-c can break
    for (var i = 0; i < 100; i++) {
      if (workspace.loaded()) {
        break
      }
      delay(1)
    }
    if (i == 3) {
      console.log(`workspace loaded timedout, try again later`)
      ObjC.import('stdlib')                               // for exit
      $.exit(16)
    }
  }
  var scheme = argv[1];
  if (scheme == "." || !scheme) {
    // seems no need to use scheme furthur
    // console.log("get active scheme")
    scheme = workspace.activeScheme()
    console.log(`active scheme is ${scheme.name()}`)
  } else {
    console.log(`get scheme by ${scheme}`)
    var scheme = workspace.schemes.byName(scheme)
    if (!scheme.exists()) {
      console.log("scheme not exist in workspace")
      //var schemes = workspace.schemes()
      //console.log(`available is ${Automation.getDisplayString(schemes)}`)
      return
    }
    console.log(`active scheme ${scheme.name()}`);
    workspace.activeScheme = scheme
  }

  console.log("build");
  workspace.build();
  // TODO: query build status //
}
