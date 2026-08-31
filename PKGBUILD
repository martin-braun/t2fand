# Maintainer: Martin Braun <martin-braun@w9mail.com>
pkgname=t2fand
pkgver=2.0.1
pkgrel=2
pkgdesc="Python daemon for T2 Mac fan control with OpenRC service definition"
arch=('x86_64')
url='https://github.com/martin-braun/t2fand'
license=('GPL3')
depends=('linux-t2' 'python' 'util-linux')
makedepends=('git')
source=('t2fand' 't2fand.initd' 't2fand.confd' 'Makefile')
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP')
backup=('etc/conf.d/t2fand')

package() {
    make DESTDIR="$pkgdir" install
}
