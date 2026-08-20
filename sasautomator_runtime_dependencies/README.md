# SASautomator runtime dependencies

This folder replaces committing `.venv311`. It contains the Python packages required to run `SASautomator.py` from source on 64-bit Windows with Python 3.11.

Create and populate the virtual environment from the repository root:

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install -r .\sasautomator_runtime_dependencies\requirements.txt
```

`pyquicktest` and `pysaelib` are IGT packages. The installer must have access to the appropriate internal package source or locally supplied wheels for those two packages.

This does not include the proprietary .NET DLLs used to send snippets. Provide the UGF DLL folder through `SASAUTOMATOR_DOTNET_RUNTIME_DIR` and the SGF DLL folder through `SASAUTOMATOR_SGFHD_DOTNET_RUNTIME_DIR` (or retain the existing runtime folders described in the project documentation).