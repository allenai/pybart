import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pybart-nlp",
    version="3.2.5",
    author="Aryeh Tiktinsky",
    author_email="aryehgigi@gmail.com",
    description="python converter from UD-tree to BART-graph representations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/allenai/pybart",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7, <3.9',
)
