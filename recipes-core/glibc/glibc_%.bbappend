# Drop support/test-run-command from glibc's do_compile target list.
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
# effect. arm64 targets do not exercise the static-pie test-binary
# link path and were not affected, but stripping the rule on every
# tune is a no-op for them.
#
# Revert this bbappend once oe-core picks up the upstream glibc fix
# (or once we move past glibc 2.43).

do_compile:prepend() {
    if [ -f "${S}/support/Makefile" ] && grep -q "test-run-command" "${S}/support/Makefile"; then
        sed -i 's/\btest-run-command\b//g' "${S}/support/Makefile"
    fi
}
