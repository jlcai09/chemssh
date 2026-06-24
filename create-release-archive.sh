#!/usr/bin/env bash
set -euo pipefail

# ChemSSH Release Archive Script
# Creates a clean release archive with a pre-built frontend.
# Version is automatically read from backend/app/__init__.py.

VERSION=$(
    sed -n 's/^__version__[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' backend/app/__init__.py | head -n 1
)

if [ -z "$VERSION" ]; then
    echo "Error: Could not read version from backend/app/__init__.py"
    exit 1
fi

OUTPUT_DIR=${1:-"release"}
RELEASE_NAME="chemssh-${VERSION}"

checksum() {
    local file=$1

    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" > "${file}.sha256"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file" > "${file}.sha256"
    else
        echo "Error: sha256sum or shasum is required to generate checksums"
        exit 1
    fi
}

copy_if_exists() {
    local source=$1
    local target=$2

    if [ -e "$source" ]; then
        cp -R "$source" "$target"
    fi
}

echo "=== Creating ChemSSH Release Archive ==="
echo "Version: ${VERSION} (from backend/app/__init__.py)"
echo ""

if ! command -v zip >/dev/null 2>&1; then
    echo "Error: zip is required to create ${RELEASE_NAME}.zip"
    exit 1
fi

echo "Step 1: Building frontend..."
(
    cd frontend
    if [ -f package-lock.json ]; then
        npm ci
    else
        npm install
    fi
    npm run build
)

if [ ! -f "frontend/dist/index.html" ]; then
    echo "Error: frontend/dist/index.html was not created"
    exit 1
fi

echo ""
echo "Step 2: Staging release files..."
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR_ABS=$(cd "$OUTPUT_DIR" && pwd)
PACKAGE_DIR="${OUTPUT_DIR_ABS}/${RELEASE_NAME}"

case "$PACKAGE_DIR" in
    "$OUTPUT_DIR_ABS"/chemssh-*)
        rm -rf "$PACKAGE_DIR"
        ;;
    *)
        echo "Error: Refusing to clean unexpected package directory: $PACKAGE_DIR"
        exit 1
        ;;
esac

mkdir -p "$PACKAGE_DIR"

cp -R backend "$PACKAGE_DIR/"
cp pyproject.toml "$PACKAGE_DIR/"
cp config.yaml "$PACKAGE_DIR/"
cp README.md "$PACKAGE_DIR/"
cp README.zh-CN.md "$PACKAGE_DIR/"
copy_if_exists LICENSE "$PACKAGE_DIR/"

if [ -d docs ]; then
    mkdir -p "$PACKAGE_DIR/docs"
    find docs -maxdepth 1 -type f -name "*.md" -exec cp {} "$PACKAGE_DIR/docs/" \;
fi

copy_if_exists plugins "$PACKAGE_DIR/"

mkdir -p "$PACKAGE_DIR/frontend"
cp -R frontend/dist "$PACKAGE_DIR/frontend/"

echo ""
echo "Step 3: Cleaning staged files..."
find "$PACKAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name ".DS_Store" -delete 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name ".chemssh-plugin-state.json" -delete 2>/dev/null || true

echo ""
echo "Step 4: Creating archives..."
rm -f "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.tar.gz" \
    "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.tar.gz.sha256" \
    "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.zip" \
    "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.zip.sha256"
tar -czf "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.tar.gz" -C "$OUTPUT_DIR_ABS" "$RELEASE_NAME"
(
    cd "$OUTPUT_DIR_ABS"
    zip -r -q "${RELEASE_NAME}.zip" "$RELEASE_NAME"
)

echo ""
echo "Step 5: Generating checksums..."
(
    cd "$OUTPUT_DIR_ABS"
    checksum "${RELEASE_NAME}.tar.gz"
    checksum "${RELEASE_NAME}.zip"
)

echo ""
echo "=== Release Archive Created! ==="
echo ""
echo "Files:"
echo "  ${OUTPUT_DIR}/${RELEASE_NAME}/"
echo "  ${OUTPUT_DIR}/${RELEASE_NAME}.tar.gz"
echo "  ${OUTPUT_DIR}/${RELEASE_NAME}.zip"
echo ""
echo "Checksums:"
cat "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.tar.gz.sha256"
cat "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.zip.sha256"
echo ""
echo "Package size:"
du -h "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.tar.gz"
du -h "${OUTPUT_DIR_ABS}/${RELEASE_NAME}.zip"
echo ""
echo "Ready to upload to GitHub Releases!"
echo ""
echo "Upload command:"
echo "  gh release create v${VERSION} \\"
echo "    ${OUTPUT_DIR}/${RELEASE_NAME}.tar.gz \\"
echo "    ${OUTPUT_DIR}/${RELEASE_NAME}.tar.gz.sha256 \\"
echo "    ${OUTPUT_DIR}/${RELEASE_NAME}.zip \\"
echo "    ${OUTPUT_DIR}/${RELEASE_NAME}.zip.sha256"
