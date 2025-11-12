# konflux-tool

The tool for checking the state of the Konflux builds.

## Usage

```bash
./konflux-tool -h
A CLI tool for managing Konflux components.

The tool expects ./bundle-patch/bundle.env to have comments in the format:
# konflux component: <component-name>
for every component that should be checked.

Usage:
  konflux-tool [command]

Available Commands:
  check-bundle  Check if pullspecs in bundle.env are up to date
  check-release Check if bundle.env images are included in the latest snapshot and find the corresponding release
  completion    Generate the autocompletion script for the specified shell
  help          Help about any command

Flags:
  -h, --help   help for konflux-tool

Use "konflux-tool [command] --help" for more information about a command.
```
