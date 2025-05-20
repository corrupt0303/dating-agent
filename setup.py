from setuptools import setup, find_packages
import os

with open("requirements.txt") as f:
    required = f.read().splitlines()

# Optional: Read README for long description
with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="dating-agent",
    version="0.1.0",
    description="AI-powered dating and classified agent with Playwright and LLM integration.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    packages=find_packages(include=["runtime*", "app*", "llm*", "frontend*", "test*", "locanto*", "proxy*", "stat*", "tags*"]),
    include_package_data=True,
    install_requires=required,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "dating-agent=runtime.dating:main"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

# Post-install: Install Playwright browsers (if not already installed)
try:
    import subprocess
    subprocess.run(["playwright", "install"], check=True)
except Exception as e:
    print("[WARNING] Playwright browsers were not installed automatically. Run 'playwright install' manually if needed.")
