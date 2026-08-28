# Maintainer: Martin Braun <martin-braun@w9mail.com>
pkgname=t2fand
pkgver=2.0.0
pkgrel=1
pkgdesc="Python daemon for T2 Mac fan control with OpenRC service definition"
arch=('x86_64')
license=('GPL3')
depends=('linux-t2' 'python' 'util-linux')
makedepends=('git')
source=("src::git+https://github.com/martin-braun/t2fand.git")
sha256sums=('SKIP')

build() {
 echo "No build needed"
}

package() {
    cd "$srcdir/src"
    install -Dm700 t2fand "$pkgdir/usr/bin/t2fand"
    install -Dm755 t2fand.initd "$pkgdir/etc/init.d/t2fand"
}
