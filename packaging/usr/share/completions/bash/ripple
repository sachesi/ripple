_ripple()
{
  local cur prev
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"

  local opts="--help --configure --remove-old --lock --unlock --list --list-remote --download"
  local slugs="ge-proton dw-proton cachyos-proton em-proton umu"

  case "$prev" in
    --list-remote)
      COMPREPLY=( $(compgen -W "$slugs" -- "$cur") )
      return 0
      ;;
    --lock|--unlock|--download)
      return 0
      ;;
  esac

  COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
  return 0
}
complete -F _ripple ripple
