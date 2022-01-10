from operator import sub
import pytest
import pymskt as mskt
import numpy as np
import SimpleITK as sitk
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk
from numpy.testing import assert_allclose


try:
    downsampled_femur_mesh = mskt.mesh.io.read_vtk('data/femur_thickness_mm_10k_pts.vtk')
    cropped_femur_mesh = mskt.mesh.io.read_vtk('data/femur_cropped_cartilage_thick_roi_10k_pts.vtk')
    smoothed_femur_mesh = mskt.mesh.io.read_vtk('data/femur_cropped_cartilage_thick_smoothed_1.25_sigma_10k_pts.vtk')
except OSError:
    downsampled_femur_mesh = mskt.mesh.io.read_vtk('../data/femur_thickness_mm_10k_pts.vtk')
    cropped_femur_mesh = mskt.mesh.io.read_vtk('../data/femur_cropped_cartilage_thick_roi_10k_pts.vtk')
    smoothed_femur_mesh = mskt.mesh.io.read_vtk('../data/femur_cropped_cartilage_thick_smoothed_1.25_sigma_10k_pts.vtk')

def test_cropped_femur_cartilage_smoothed():
    femur = mskt.mesh.BoneMesh(path_seg_image='data/right_knee_example.nrrd', 
                               label_idx=5, 
                               list_cartilage_labels=[1], 
                               crop_percent=0.7)
    femur.create_mesh()
    femur.resample_surface()
    femur.calc_cartilage_thickness()
    femur.smooth_surface_scalars(scalar_sigma=1.25)

    # compare calcualted cartilage thickness w/ thickness of saved result that has been checked. 
    ref_smoothed_femur_mesh_thickness = vtk_to_numpy(smoothed_femur_mesh.GetPointData().GetArray('thickness (mm)'))
    smoothed_femur_mesh_thickness = vtk_to_numpy(femur._mesh.GetPointData().GetArray('thickness (mm)'))
    assert_allclose(smoothed_femur_mesh_thickness, ref_smoothed_femur_mesh_thickness)


def test_cropped_femur_cartilage_region_assignment():
    femur = mskt.mesh.BoneMesh(path_seg_image='data/right_knee_example.nrrd', 
                               label_idx=5, 
                               list_cartilage_labels=[1], 
                               crop_percent=0.7)
    femur.create_mesh()
    femur.resample_surface()
    # femur.calc_cartilage_thickness()  # DONT NEED THIS FOR THIS TEST.... MAYBE CREATE NEW TEST INCLUDING THIS? 
    femur.assign_cartilage_regions()

    # compare cartilage ROI between new calculation & saved mesh. 
    ref_cropped_femur_mesh_roi = vtk_to_numpy(cropped_femur_mesh.GetPointData().GetArray('labels'))
    cropped_femur_mesh_roi = vtk_to_numpy(femur._mesh.GetPointData().GetArray('labels'))
    assert_allclose(cropped_femur_mesh_roi, ref_cropped_femur_mesh_roi)

    # compare the x/y/z position of the points on the mesh
    ref_pts = mskt.mesh.get_mesh_physical_point_coords(cropped_femur_mesh)
    new_pts = femur.point_coords
    assert_allclose(ref_pts, new_pts)


def test_cropped_femur_using_integrated_bone_cartilage_thickness_calc():
    # Create new mesh & calculate cartilge thickness
    femur = mskt.mesh.BoneMesh(path_seg_image='data/right_knee_example.nrrd', 
                               label_idx=5, 
                               list_cartilage_labels=[1], 
                               crop_percent=0.7)
    femur.create_mesh()
    femur.resample_surface()
    femur.calc_cartilage_thickness()

    # compare calcualted cartilage thickness w/ thickness of saved result that has been checked. 
    ref_cropped_femur_mesh_thickness = vtk_to_numpy(cropped_femur_mesh.GetPointData().GetArray('thickness (mm)'))
    cropped_femur_mesh_thickness = vtk_to_numpy(femur._mesh.GetPointData().GetArray('thickness (mm)'))
    assert_allclose(cropped_femur_mesh_thickness, ref_cropped_femur_mesh_thickness)

    # compare the x/y/z position of the points on the mesh
    ref_pts = mskt.mesh.get_mesh_physical_point_coords(cropped_femur_mesh)
    new_pts = femur.point_coords
    assert_allclose(ref_pts, new_pts)


def test_femur_cart_thick_roi_calc(timing=False):
    femur = mskt.mesh.BoneMesh(path_seg_image='data/right_knee_example.nrrd', label_idx=5)
    femur.create_mesh()
    femur.resample_surface(subdivisions=2, clusters=10000)

    seg_vtk_image_reader = mskt.image.read_nrrd('data/right_knee_example.nrrd', set_origin_zero=True)
    seg_vtk_image = seg_vtk_image_reader.GetOutput()
    seg_sitk_image = sitk.ReadImage('data/right_knee_example.nrrd')
    seg_transformer = mskt.mesh.meshTransform.SitkVtkTransformer(seg_sitk_image)

    fem_cartilage = mskt.mesh.BoneMesh(path_seg_image='data/right_knee_example.nrrd', label_idx=1)
    fem_cartilage.create_mesh()

    fem_cartilage.apply_transform_to_mesh(transform=seg_transformer.get_inverse_transform())
    femur.apply_transform_to_mesh(transform=seg_transformer.get_inverse_transform())


    result = mskt.mesh.meshTools.get_cartilage_properties_at_points(femur._mesh, fem_cartilage._mesh, seg_vtk_image=seg_vtk_image, ray_cast_length=7., percent_ray_length_opposite_direction=0.25)

    thickness_scalars = numpy_to_vtk(result[0])
    thickness_scalars.SetName('thickness (mm)')
    femur._mesh.GetPointData().AddArray(thickness_scalars)

    cartilage_roi = numpy_to_vtk(result[1])
    cartilage_roi.SetName('cartilage_region')
    femur._mesh.GetPointData().AddArray(cartilage_roi)

    femur.reverse_all_transforms()
    fem_cartilage.reverse_all_transforms()

    downsampled_femur_mesh_thickness = vtk_to_numpy(downsampled_femur_mesh.GetPointData().GetArray('thickness (mm)'))
    downsampled_femur_mesh_cart_roi = vtk_to_numpy(downsampled_femur_mesh.GetPointData().GetArray('cartilage_region'))

    assert_allclose(result[0], downsampled_femur_mesh_thickness)
    assert_allclose(result[1], downsampled_femur_mesh_cart_roi)

if __name__ == "__main__":
    import time
    test_femur_cart_thick_roi_calc(timing=True, verbose=True)