# Publish Agent Utka from a clean source archive

Build the archive from the application folder, using an output filename that does not exist.

~~~powershell
python .\scripts\build_source_release.py ..\agent-utka-source.zip
~~~

The script has an explicit list of public source, docs, and generic tests. The ZIP leaves out runtime downloads, the Python environment, local settings, indexes, history, recordings, and workspace materials. It includes a root `LICENSE` and `NOTICE` if present. The archive is a review copy until the repository owner has selected a license and reviewed the actual files.

1. Extract the archive into a new directory. Review the file list and run the checks in the [tutorial](tutorial.md#verify-the-installation).
2. Add the license approved by the project owner. Python dependencies, Ollama, and downloaded models have their own licenses. The source archive contains none of their binaries or model weights.
3. On GitHub, create an empty public repository. Initialize Git in the extracted directory and check the files to be staged. Set the remote to the URL of the repository you created.

   ~~~powershell
   git init -b main
   git add --dry-run .
   git add .
   git status --short
   git commit -m "Initial Agent Utka source release"
   git remote add origin https://github.com/YOUR-ACCOUNT/agent-utka.git
   git push -u origin main
   ~~~

4. Open the GitHub repository as a signed-out visitor and check that the README, tutorial links, example file, and license are visible. The [GitHub guide to adding local code](https://docs.github.com/en/repositories/creating-and-managing-repositories/adding-locally-hosted-code-to-github) covers authentication and repository setup.

If you attach a ZIP to a GitHub Release, create a fresh one from the reviewed source and license. Keep user settings and model data on the machine that runs the app.
