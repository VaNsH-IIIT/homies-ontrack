# Getting the data

Needs ~10 GB free (unzipped) plus the 2.3 GB zip. Put it **outside the repo** on a drive with space, then point `MAPLE_DATA_DIR` in `.env` at the unzipped folder.

```bash
pip install -U huggingface_hub
hf download nuxsh/maple-collections-hackathon --repo-type dataset --local-dir D:/maple_data
cd D:/maple_data && unzip maple_collections_release.zip
```

- Skip `maple_collections_voice.zip` (2.4 GB): our design uses voice through transcripts only, with no acoustic features.
- Read `maple_collections_release/README.md` first: file conventions, loading code, and the customer key each source system uses.
- Delete the zip after unzipping if disk is tight.
