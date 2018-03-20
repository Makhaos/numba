from __future__ import print_function, absolute_import, division

import numpy as np
from numba import cuda, int32, float32
from numba.cuda.testing import unittest, SerialMixin, skip_on_cudasim


def simple_threadidx(ary):
    i = cuda.threadIdx.x
    ary[0] = i


def fill_threadidx(ary):
    i = cuda.threadIdx.x
    ary[i] = i


def fill3d_threadidx(ary):
    i = cuda.threadIdx.x
    j = cuda.threadIdx.y
    k = cuda.threadIdx.z

    ary[i, j, k] = (i + 1) * (j + 1) * (k + 1)


def simple_grid1d(ary):
    i = cuda.grid(1)
    ary[i] = i


def simple_grid2d(ary):
    i, j = cuda.grid(2)
    ary[i, j] = i + j


def simple_gridsize1d(ary):
    i = cuda.grid(1)
    x = cuda.gridsize(1)
    if i == 0:
        ary[0] = x


def simple_gridsize2d(ary):
    i, j = cuda.grid(2)
    x, y = cuda.gridsize(2)
    if i == 0 and j == 0:
        ary[0] = x
        ary[1] = y


def intrinsic_forloop_step(c):
    startX, startY = cuda.grid(2)
    gridX = cuda.gridDim.x * cuda.blockDim.x
    gridY = cuda.gridDim.y * cuda.blockDim.y
    height, width = c.shape

    for x in range(startX, width, gridX):
        for y in range(startY, height, gridY):
            c[y, x] = x + y


def simple_popc(ary, c):
    ary[0] = cuda.popc(c)


def simple_brev(ary, c):
    ary[0] = cuda.brev(c)


def simple_clz(ary, c):
    ary[0] = cuda.clz(c)


class TestCudaIntrinsic(SerialMixin, unittest.TestCase):
    def test_simple_threadidx(self):
        compiled = cuda.jit("void(int32[:])")(simple_threadidx)
        ary = np.ones(1, dtype=np.int32)
        compiled(ary)
        self.assertTrue(ary[0] == 0)

    def test_fill_threadidx(self):
        compiled = cuda.jit("void(int32[:])")(fill_threadidx)
        N = 10
        ary = np.ones(N, dtype=np.int32)
        exp = np.arange(N, dtype=np.int32)
        compiled[1, N](ary)
        self.assertTrue(np.all(ary == exp))

    def test_fill3d_threadidx(self):
        X, Y, Z = 4, 5, 6

        def c_contigous():
            compiled = cuda.jit("void(int32[:,:,::1])")(fill3d_threadidx)
            ary = np.zeros((X, Y, Z), dtype=np.int32)
            compiled[1, (X, Y, Z)](ary)
            return ary

        def f_contigous():
            compiled = cuda.jit("void(int32[::1,:,:])")(fill3d_threadidx)
            ary = np.asfortranarray(np.zeros((X, Y, Z), dtype=np.int32))
            compiled[1, (X, Y, Z)](ary)
            return ary

        c_res = c_contigous()
        f_res = f_contigous()
        self.assertTrue(np.all(c_res == f_res))

    def test_simple_grid1d(self):
        compiled = cuda.jit("void(int32[::1])")(simple_grid1d)
        ntid, nctaid = 3, 7
        nelem = ntid * nctaid
        ary = np.empty(nelem, dtype=np.int32)
        compiled[nctaid, ntid](ary)
        self.assertTrue(np.all(ary == np.arange(nelem)))

    def test_simple_grid2d(self):
        compiled = cuda.jit("void(int32[:,::1])")(simple_grid2d)
        ntid = (4, 3)
        nctaid = (5, 6)
        shape = (ntid[0] * nctaid[0], ntid[1] * nctaid[1])
        ary = np.empty(shape, dtype=np.int32)
        exp = ary.copy()
        compiled[nctaid, ntid](ary)

        for i in range(ary.shape[0]):
            for j in range(ary.shape[1]):
                exp[i, j] = i + j

        self.assertTrue(np.all(ary == exp))

    def test_simple_gridsize1d(self):
        compiled = cuda.jit("void(int32[::1])")(simple_gridsize1d)
        ntid, nctaid = 3, 7
        ary = np.zeros(1, dtype=np.int32)
        compiled[nctaid, ntid](ary)
        self.assertEqual(ary[0], nctaid * ntid)

    def test_simple_gridsize2d(self):
        compiled = cuda.jit("void(int32[::1])")(simple_gridsize2d)
        ntid = (4, 3)
        nctaid = (5, 6)
        ary = np.zeros(2, dtype=np.int32)
        compiled[nctaid, ntid](ary)

        self.assertEqual(ary[0], nctaid[0] * ntid[0])
        self.assertEqual(ary[1], nctaid[1] * ntid[1])

    def test_intrinsic_forloop_step(self):
        compiled = cuda.jit("void(float32[:,::1])")(intrinsic_forloop_step)
        ntid = (4, 3)
        nctaid = (5, 6)
        shape = (ntid[0] * nctaid[0], ntid[1] * nctaid[1])
        ary = np.empty(shape, dtype=np.int32)

        compiled[nctaid, ntid](ary)

        gridX, gridY = shape
        height, width = ary.shape
        for i, j in zip(range(ntid[0]), range(ntid[1])):
            startX, startY = gridX + i, gridY + j
            for x in range(startX, width, gridX):
                for y in range(startY, height, gridY):
                    self.assertTrue(ary[y, x] == x + y, (ary[y, x], x + y))

    def test_3dgrid(self):
        @cuda.jit
        def foo(out):
            x, y, z = cuda.grid(3)
            a, b, c = cuda.gridsize(3)
            out[x, y, z] = a * b * c

        arr = np.zeros(9 ** 3, dtype=np.int32).reshape(9, 9, 9)
        foo[(3, 3, 3), (3, 3, 3)](arr)

        np.testing.assert_equal(arr, 9 ** 3)

    def test_3dgrid_2(self):
        @cuda.jit
        def foo(out):
            x, y, z = cuda.grid(3)
            a, b, c = cuda.gridsize(3)
            grid_is_right = (
                x == cuda.threadIdx.x + cuda.blockIdx.x * cuda.blockDim.x and
                y == cuda.threadIdx.y + cuda.blockIdx.y * cuda.blockDim.y and
                z == cuda.threadIdx.z + cuda.blockIdx.z * cuda.blockDim.z
            )
            gridsize_is_right = (a == cuda.blockDim.x * cuda.gridDim.x and
                                 b == cuda.blockDim.y * cuda.gridDim.y and
                                 c == cuda.blockDim.z * cuda.gridDim.z)
            out[x, y, z] = grid_is_right and gridsize_is_right

        x, y, z = (4 * 3, 3 * 2, 2 * 4)
        arr = np.zeros((x * y * z), dtype=np.bool).reshape(x, y, z)
        foo[(4, 3, 2), (3, 2, 4)](arr)

        self.assertTrue(np.all(arr))

    def test_popc_u4(self):
        compiled = cuda.jit("void(int32[:], uint32)")(simple_popc)
        ary = np.zeros(1, dtype=np.int32)
        compiled(ary, 0xF0)
        self.assertEquals(ary[0], 4)

    def test_popc_u8(self):
        compiled = cuda.jit("void(int32[:], uint64)")(simple_popc)
        ary = np.zeros(1, dtype=np.int32)
        compiled(ary, 0xF00000000000)
        self.assertEquals(ary[0], 4)

    def test_brev_u4(self):
        compiled = cuda.jit("void(uint32[:], uint32)")(simple_brev)
        ary = np.zeros(1, dtype=np.uint32)
        compiled(ary, 0x0000_30F0)
        self.assertEquals(ary[0], 0x0F0C_0000)

    @skip_on_cudasim('only get given a Python "int", assumes 32 bits')
    def test_brev_u8(self):
        compiled = cuda.jit("void(uint64[:], uint64)")(simple_brev)
        ary = np.zeros(1, dtype=np.uint64)
        compiled(ary, 0x0000_30F0_0000_30F0)
        self.assertEquals(ary[0], 0x0F0C_0000_0F0C_0000)

    def test_clz_i4(self):
        compiled = cuda.jit("void(int32[:], int32)")(simple_clz)
        ary = np.zeros(1, dtype=np.int32)
        compiled(ary, 0x0010_0000)
        self.assertEquals(ary[0], 11)

    def test_clz_i4_1s(self):
        compiled = cuda.jit("void(int32[:], int32)")(simple_clz)
        ary = np.zeros(1, dtype=np.int32)
        compiled(ary, 0xFFFF_FFFF)
        self.assertEquals(ary[0], 0)

    def test_clz_i4_0s(self):
        compiled = cuda.jit("void(int32[:], int32)")(simple_clz)
        ary = np.zeros(1, dtype=np.int32)
        compiled(ary, 0x0)
        self.assertEquals(ary[0], 32, "CUDA semantics")

    @skip_on_cudasim('only get given a Python "int", assumes 32 bits')
    def test_clz_i8(self):
        compiled = cuda.jit("void(int32[:], int64)")(simple_clz)
        ary = np.zeros(1, dtype=np.int32)
        compiled(ary, 0x0000_0000_0010_000)
        self.assertEquals(ary[0], 43)


if __name__ == '__main__':
    unittest.main()
