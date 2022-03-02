import numpy as np
from datetime import date
import os


from pymskt.mesh.meshRegistration import get_icp_transform, non_rigidly_register
from pymskt.mesh.meshTools import get_mesh_physical_point_coords, set_mesh_physical_point_coords
from pymskt.mesh.meshTransform import apply_transform
from pymskt.mesh.utils import get_symmetric_surface_distance, vtk_deep_copy
from pymskt.mesh import io 

today = date.today()

class FindReferenceMeshICP:
    """
    For list of meshes perform all possible ICP registrations to identify mesh with smallest
    surface error to all other meshes. 

    Parameters
    ----------
    list_meshes : _type_
        _description_
    """

    def __init__(
        self,
        list_mesh_paths,
        max_n_iter=1000,
        n_landmarks=1000,
        reg_mode='similarity',
        verbose=True
    ):
        """
        Perform ICP registration between all pairs of meshes. Calculate
        symmetric surface distance for all registered meshes. Find target
        mesh with smallest mean surface error to all other meshes. 

        This smallest error mesh is the refrence mesh for the next step of
        SSM pipelines (procrustes using non-rigid registration)

        Parameters
        ----------
        list_mesh_paths : _type_
            _description_
        max_n_iter : int, optional
            _description_, by default 1000
        n_landmarks : int, optional
            _description_, by default 1000
        reg_mode : str, optional
            _description_, by default 'similarity'
        verbose : bool, optional
            _description_, by default True
        """
        self.list_mesh_paths = list_mesh_paths
        self.n_meshes = len(list_mesh_paths)
        self._symm_surface_distances = np.zeros((self.n_meshes, self.n_meshes), dtype=float)
        self.mean_errors = None

        self.max_n_iter = max_n_iter
        self.n_landmarks = n_landmarks
        self.reg_mode = reg_mode

        self.verbose=verbose

        self._ref_idx = None
        self._ref_path = None


    def register_meshes(self, idx1_target, idx2_source):
        target = io.read_vtk(self.list_mesh_paths[idx1_target])
        source = io.read_vtk(self.list_mesh_paths[idx2_source])

        icp_transform = get_icp_transform(
            source, 
            target, 
            max_n_iter=self.max_n_iter, 
            n_landmarks=self.n_landmarks, 
            reg_mode=self.reg_mode
        )

        transformed_source = apply_transform(source, icp_transform)

        symmetric_surf_distance = get_symmetric_surface_distance(target, transformed_source)

        self._symm_surface_distances[idx1_target, idx2_source] = symmetric_surf_distance
    
    def get_template_idx(self):
        self._mean_errors = np.mean(self._symm_surface_distances, axis=1)
        self._ref_idx = np.argmin(self._mean_errors)
        self._ref_path = self.list_mesh_paths[self._ref_idx]


    def execute(self):
        if self.verbose is True:
            print(f'Starting registrations, there are {len(self.list_mesh_paths)} meshes')
        for idx1_target, target_path in enumerate(self.list_mesh_paths):
            if self.verbose is True:
                print(f'\tStarting target mesh {idx1_target}')
            for idx2_source, source_path in enumerate(self.list_mesh_paths):
                if self.verbose is True:
                    print(f'\t\tStarting source mesh {idx2_source}')
                # If the target & mesh are same skip, errors = 0
                if idx1_target == idx2_source:
                    continue
                else:
                    self.register_meshes(idx1_target, idx2_source)
        if self.verbose is True:
            print('Finished all registrations!')
        
        self.get_template_idx()
    
    @property
    def ref_idx(self):
        return self._ref_idx
    
    @property
    def ref_path(self):
        return self._ref_path
    
    @property
    def symm_surface_distances(self):
        return self._symm_surface_distances
    
    @property
    def mean_errors(self):
        return self._mean_errors
    

class ProcrustesRegistration:
    # https://en.wikipedia.org/wiki/Generalized_Procrustes_analysis
    def __init__(
        self,
        path_ref_mesh,
        list_mesh_paths,
        tolerance = 1e-3,
        max_n_registration_steps=10,
        verbose=True,
        **kwargs
    ):
        self.path_ref_mesh = path_ref_mesh
        self.list_mesh_paths = list_mesh_paths
        # Ensure that path_ref_mesh is in list & at index 0
        if self.path_ref_mesh in self.list_mesh_paths:
            path_ref_idx = self.list_mesh_paths.index(self.path_ref_mesh)
            self.list_mesh_paths.pop(path_ref_idx)
        self.list_mesh_paths.insert(0, self.path_ref_mesh)


        self._ref_mesh = io.read_vtk(self.path_ref_mesh)
        self.n_points = self._ref_mesh.GetNumberOfPoints()

        self.mean_mesh = None

        self.tolerance = tolerance
        self.max_n_registration_steps = max_n_registration_steps

        self.kwargs = kwargs
        # Ensure that the source mesh (mean, or reference) is the bse mesh
        # We want all meshes aligned with this reference. Then we want
        # to apply a "warp" of the ref/mean mesh to make it 
        self.kwargs['icp_register_first'] = True
        self.kwargs['icp_reg_target_to_source'] = True

        self._registered_pt_coords = np.zeros((len(list_mesh_paths) + 1, self.n_points, 3), dtype=float)
        self._registered_pt_coords[0, :, :] = get_mesh_physical_point_coords(self._ref_mesh)

        self.ref_2_mean_error = 100
        self.reg_idx = 0

        self.verbose = verbose

    def register(self, ref_mesh_source, other_mesh_idx):
        target_mesh = io.read_vtk(self.list_mesh_paths[other_mesh_idx])

        registered_mesh = non_rigidly_register(
            target_mesh=target_mesh,
            source_mesh=ref_mesh_source,
            **self.kwargs
        )

        self._registered_pt_coords[other_mesh_idx, :, :] = get_mesh_physical_point_coords(registered_mesh)
    
    def execute(self):

        while (self.reg_idx < self.max_n_registration_steps) & (self.ref_2_mean_error > self.tolerance):
            if self.verbose is True:
                print(f'Starting registration round {self.reg_idx}')
            # register the reference mesh to all other meshes
            for idx, path in enumerate(self.list_mesh_paths):
                if self.verbose is True:
                    print(f'\tRegistering to mesh # {idx}')
                # skip the first mesh in the list if its the first round (its the reference)
                if (self.reg_idx == 0) & (idx == 0):
                    continue
                # register & save registered coordinates in the pre-allocated array
                self.register(self._ref_mesh, idx)
            
            # Calculate the mean bone shape & create new mean bone shape mesh
            mean_shape = np.mean(self._registered_pt_coords, axis=0)
            mean_mesh = vtk_deep_copy(self._ref_mesh)
            set_mesh_physical_point_coords(mean_mesh, mean_shape)

            # Get surface distance between previous reference mesh and the new mean
            self.ref_2_mean_error = get_symmetric_surface_distance(self._ref_mesh, mean_mesh)
            if self.verbose is True:
                print(f'\t\tSymmetric surface error: {self.ref_2_mean_error}')
            
            # update _ref_mesh
            self._ref_mesh = mean_mesh
                
            self.reg_idx += 1
    
    def save_meshes(
        self, 
        mesh_suffix=f'procrustes_registered_{today.strftime("%b")}_{today.day}_{today.year}',
        folder=None
    ):
        mesh = vtk_deep_copy(self._ref_mesh)
        for idx, path in enumerate(self.list_mesh_paths):
            # parse folder / filename for saving
            orig_folder = os.path.dirname(path)
            orig_filename = os.path.basename(path)
            base_filename = orig_filename[: orig_filename.rfind(".")]
            filename = f'{base_filename}_{mesh_suffix}_{idx}.vtk'
            if folder is None:
                path_to_save = os.path.join(orig_folder, filename)
            else:
                path_to_save = os.path.join(folder, filename)        
            
            # Keep recycling the same base mesh, just move the x/y/z point coords around. 
            set_mesh_physical_point_coords(mesh, self._registered_pt_coords[idx, :, :])
            # save mesh to disk
            io.write_vtk(mesh, path_to_save)
    
    def save_ref_mesh(self, path):
        io.write_vtk(self._ref_mesh, path)

    @property
    def ref_mesh(self):
        return self._ref_mesh
    
    @property
    def registered_pt_coords(self):
        return self._registered_pt_coords
    