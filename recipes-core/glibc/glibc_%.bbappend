# Two glibc 2.43 + meta-intel + oe-core master ergonomic fixes.
#
# 1. Drop support/test-run-command from do_compile.
#
# glibc 2.43 on x86_64 fails to link this testsuite-only binary
# statically because __run_prefork_handlers / __run_postfork_handlers
# (hidden symbols defined in posix/register-atfork.c) are not packed
# into libc.a for the --static-pie link path:
#
#   .../libc.a(fork.o): in function `__libc_fork':
#     fork.c:51:  undefined reference to `__run_prefork_handlers'
#     fork.c:113: undefined reference to `__run_postfork_handlers'
#   support/test-run-command: hidden symbol `__run_prefork_handlers'
#     isn't defined
#   final link failed: bad value
#
# The binary is used only by glibc's own `make check` testsuite; it
# is never installed into the rootfs and removing it has no runtime
# effect.
#
# Use line-delete (sed /pat/d) rather than word-substitute. A bare
# 's/\btest-run-command\b//g' also matches inside identifiers like
# LDLIBS-test-run-command and leaves "LDLIBS- =" -- a malformed Make
# variable name that bites later phases. Line-delete is surgical:
# drop every line that mentions the test binary, none of which exist
# in production paths.
do_compile:prepend() {
    if [ -f "${S}/support/Makefile" ]; then
        sed -i '/test-run-command/d' "${S}/support/Makefile"
    fi
}

# 2. Skip do_package debug-info processing on libc.a.
#
# oe-core's source_info() in lib/oe/package.py runs dwarfsrcfiles on
# every static library it finds. dwarfsrcfiles (from debugedit-native)
# cannot read the libc.a archive layout glibc 2.43 emits on x86_64
# and fails with "not a valid ELF file" even though libc.a is a
# perfectly valid AR archive (!<arch>\n magic, ar t lists members
# fine). arm64 tunes don't trigger the same code path. Failure looks
# like:
#
#   ERROR: glibc-2.43+git-r1 do_package: dwarfsrcfiles failed with
#     exit code 1 (cmd was ['dwarfsrcfiles',
#     '/build/.../glibc/2.43+git/package/usr/lib/libc.a'])
#   dwarfsrcfiles: .../libc.a: not a valid ELF file
#
# INHIBIT_PACKAGE_DEBUG_SPLIT = "1" skips splitdebuginfo + the static
# debug split block entirely for this recipe. We give up the
# glibc-dbg package source-index in exchange for a building matrix.
# Revert when oe-core's dwarfsrcfiles learns AR archives or glibc
# moves to a debug layout dwarfsrcfiles tolerates.
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
