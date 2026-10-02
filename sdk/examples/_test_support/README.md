# Shared example test support

`readback.py` verifies stored transcripts and tool decisions through the public
Watcher SDK. It uses only the Python standard library and `watcher_sdk`.

Native test recipes copy this directory beside their Python probe, making the
`_test_support.readback` import available in the installed fixture without the
source checkout. Keep it with the examples when extracting the source archive.
It is test support, not part of an integration's runtime package.

The helper polls an explicitly supplied SDK client and retains the responses
in the caller's evidence directory. A successful hook response alone does not
prove that a transcript or decision has been stored.
