{
  description = "Ripple: CLI tool to manage Proton builds";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;
      in
      {
        packages.ripple = python.pkgs.buildPythonApplication {
          pname = "ripple";
          version = "3.1.0";
          format = "pyproject";

          src = ./.;

          nativeBuildInputs = with python.pkgs; [
            setuptools
            wheel
          ];

          propagatedBuildInputs = with python.pkgs; [
            # Add runtime dependencies here if any are added to pyproject.toml later
          ];

          meta = with pkgs.lib; {
            description = "Download and install Proton releases with centralized storage and symlink management";
            homepage = "https://github.com/sachesi/ripple";
            license = licenses.gpl3Plus;
            maintainers = [ ];
            mainProgram = "ripple";
          };
        };

        packages.default = self.packages.${system}.ripple;

        apps.ripple = flake-utils.lib.mkApp {
          drv = self.packages.${system}.ripple;
        };
        apps.default = self.apps.${system}.ripple;

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python
            python.pkgs.setuptools
            python.pkgs.venvShellHook
          ];
          shellHook = ''
            export PYTHONPATH=$PYTHONPATH:$(pwd)/src
          '';
        };
      }
    );
}
