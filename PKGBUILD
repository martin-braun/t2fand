# Maintainer: Martin Braun <martin-braun@w9mail.com>
pkgname=t2fand
pkgver=2.0.1
pkgrel=1
pkgdesc="Python daemon for T2 Mac fan control with OpenRC service definition"
arch=('x86_64')
license=('GPL3')
depends=('linux-t2' 'python' 'util-linux')
makedepends=('git')
source=('t2fand' 't2fand.initd' 'Makefile')
sha256sums=('SKIP' 'SKIP' 'SKIP')

package() {
	make DESTDIR="$pkgdir" install
}
