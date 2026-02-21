# Radicalized
A simple wrapper around the radical python library to make it an easy to use CLI tool.
The goal is to all agentic AI to interface with self-hosted data.

> [!WARNING]
> Giving any personal data to an AI agent comes with risks of it leaking your personal data, or
tempering with it in an irreversible way.
Please be sure to:
> 1. Restrict its online interactions to avoid any prompt injections
> 2. Regularly backup your data

# Set up
You can make this script executable with
```bash
sudo ln -s ~/clawd/skills/radicale/scripts/Radicalized/cli.py /usr/local/bin/radicale
```
Make sure the shebang (#!) at the beginning of cli.py points to the real venv.