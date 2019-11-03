import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cvjmcard",
    version="0.0.1",
    author="Lukas Schreiner",
    author_email="dev+cvjm@lschreiner.de",
    description="A small client to fetch statistics and addresses from cvjm-card.de",
    long_description=long_description,
    url="https://github.com/monofox/python-cvjmcard",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)