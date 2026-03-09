#!/bin/bash
# Check prerequisites for mac-desktop-use skill

echo "=== macOS Desktop Use - Setup Check ==="
echo ""

# Check screencapture
if command -v screencapture &> /dev/null; then
    echo "[OK] screencapture (built-in)"
else
    echo "[FAIL] screencapture not found (should be built-in on macOS)"
fi

# Check cliclick
if command -v cliclick &> /dev/null; then
    echo "[OK] cliclick installed ($(cliclick -V 2>&1 || echo 'version unknown'))"
else
    echo "[MISSING] cliclick - Install with: brew install cliclick"
fi

# Check osascript
if command -v osascript &> /dev/null; then
    echo "[OK] osascript (built-in)"
else
    echo "[FAIL] osascript not found (should be built-in on macOS)"
fi

# Check Python3
if command -v python3 &> /dev/null; then
    echo "[OK] python3 ($(python3 --version 2>&1))"
else
    echo "[FAIL] python3 not found"
fi

echo ""
echo "=== Permissions Check ==="
echo "Ensure the following in System Settings > Privacy & Security:"
echo "  - Accessibility: Terminal / iTerm / your terminal app must be enabled"
echo "  - Screen Recording: Terminal / iTerm / your terminal app must be enabled"
echo ""

# Quick functional test
echo "=== Quick Test ==="
TMPFILE=$(mktemp /tmp/desktop_test_XXXXXX.png)
if screencapture -x "$TMPFILE" 2>/dev/null; then
    SIZE=$(stat -f%z "$TMPFILE" 2>/dev/null || stat --printf="%s" "$TMPFILE" 2>/dev/null)
    if [ "$SIZE" -gt 0 ]; then
        echo "[OK] Screenshot capture works (${SIZE} bytes)"
    else
        echo "[WARN] Screenshot file is empty - check Screen Recording permission"
    fi
    rm -f "$TMPFILE"
else
    echo "[FAIL] Screenshot capture failed - check Screen Recording permission"
fi

if command -v cliclick &> /dev/null; then
    POS=$(cliclick p:. 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "[OK] Mouse position read works: $POS"
    else
        echo "[FAIL] cliclick cannot read mouse - check Accessibility permission"
    fi
fi

echo ""
echo "=== Setup Complete ==="
