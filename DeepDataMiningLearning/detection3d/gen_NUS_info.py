import mmcv
import numpy as np
from tqdm import tqdm

from nuscenes.nuscenes import NuScenes
from nuscenes.utils import splits
from mmengine import dump
import mmengine
import os
from multiprocessing import Pool

import mmcv
import numpy as np
from nuscenes.utils.data_classes import LidarPointCloud, RadarPointCloud
from nuscenes.utils.geometry_utils import transform_matrix, view_points
from pyquaternion import Quaternion

from functools import reduce


def generate_info(nusc, scenes, max_cam_sweeps=6, max_lidar_sweeps=10):
    infos = list()
    for cur_scene in tqdm(nusc.scene):
        if cur_scene['name'] not in scenes:
            continue
        first_sample_token = cur_scene['first_sample_token']
        cur_sample = nusc.get('sample', first_sample_token)
        while True:
            info = dict()
            cam_datas = list()
            lidar_datas = list()
            info['scene_name'] = nusc.get('scene', cur_scene['token'])['name']
            info['sample_token'] = cur_sample['token']
            info['timestamp'] = cur_sample['timestamp']
            info['scene_token'] = cur_sample['scene_token']
            cam_names = [
                'CAM_FRONT', 'CAM_FRONT_RIGHT', 'CAM_BACK_RIGHT',
                'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_FRONT_LEFT'
            ]
            lidar_names = ['LIDAR_TOP']
            cam_infos = dict()
            lidar_infos = dict()
            for cam_name in cam_names:
                cam_data = nusc.get('sample_data',
                                    cur_sample['data'][cam_name])
                cam_datas.append(cam_data)
                sweep_cam_info = dict()
                sweep_cam_info['sample_token'] = cam_data['sample_token']
                sweep_cam_info['ego_pose'] = nusc.get(
                    'ego_pose', cam_data['ego_pose_token'])
                sweep_cam_info['timestamp'] = cam_data['timestamp']
                sweep_cam_info['is_key_frame'] = cam_data['is_key_frame']
                sweep_cam_info['height'] = cam_data['height']
                sweep_cam_info['width'] = cam_data['width']
                sweep_cam_info['filename'] = cam_data['filename']
                sweep_cam_info['calibrated_sensor'] = nusc.get(
                    'calibrated_sensor', cam_data['calibrated_sensor_token'])
                cam_infos[cam_name] = sweep_cam_info
            for lidar_name in lidar_names:
                lidar_data = nusc.get('sample_data',
                                      cur_sample['data'][lidar_name])
                lidar_datas.append(lidar_data)
                sweep_lidar_info = dict()
                sweep_lidar_info['sample_token'] = lidar_data['sample_token']
                sweep_lidar_info['ego_pose'] = nusc.get(
                    'ego_pose', lidar_data['ego_pose_token'])
                sweep_lidar_info['timestamp'] = lidar_data['timestamp']
                sweep_lidar_info['filename'] = lidar_data['filename']
                sweep_lidar_info['calibrated_sensor'] = nusc.get(
                    'calibrated_sensor', lidar_data['calibrated_sensor_token'])
                lidar_infos[lidar_name] = sweep_lidar_info

            lidar_sweeps = [dict() for _ in range(max_lidar_sweeps)]
            cam_sweeps = [dict() for _ in range(max_cam_sweeps)]
            info['cam_infos'] = cam_infos #6 cameras
            info['lidar_infos'] = lidar_infos #one item LIDAR_TOP
            for k, cam_data in enumerate(cam_datas):
                sweep_cam_data = cam_data
                for j in range(max_cam_sweeps):
                    if sweep_cam_data['prev'] == '':
                        break
                    else:
                        sweep_cam_data = nusc.get('sample_data',
                                                  sweep_cam_data['prev'])
                        sweep_cam_info = dict()
                        sweep_cam_info['sample_token'] = sweep_cam_data[
                            'sample_token']
                        if sweep_cam_info['sample_token'] != cam_data[
                                'sample_token']:
                            break
                        sweep_cam_info['ego_pose'] = nusc.get(
                            'ego_pose', cam_data['ego_pose_token'])
                        sweep_cam_info['timestamp'] = sweep_cam_data[
                            'timestamp']
                        sweep_cam_info['is_key_frame'] = sweep_cam_data[
                            'is_key_frame']
                        sweep_cam_info['height'] = sweep_cam_data['height']
                        sweep_cam_info['width'] = sweep_cam_data['width']
                        sweep_cam_info['filename'] = sweep_cam_data['filename']
                        sweep_cam_info['calibrated_sensor'] = nusc.get(
                            'calibrated_sensor',
                            cam_data['calibrated_sensor_token'])
                        cam_sweeps[j][cam_names[k]] = sweep_cam_info

            for k, lidar_data in enumerate(lidar_datas):
                sweep_lidar_data = lidar_data
                for j in range(max_lidar_sweeps):
                    if sweep_lidar_data['prev'] == '':
                        break
                    else:
                        sweep_lidar_data = nusc.get('sample_data',
                                                    sweep_lidar_data['prev'])
                        sweep_lidar_info = dict()
                        sweep_lidar_info['sample_token'] = sweep_lidar_data[
                            'sample_token']
                        if sweep_lidar_info['sample_token'] != lidar_data[
                                'sample_token']:
                            break
                        sweep_lidar_info['ego_pose'] = nusc.get(
                            'ego_pose', sweep_lidar_data['ego_pose_token'])
                        sweep_lidar_info['timestamp'] = sweep_lidar_data[
                            'timestamp']
                        sweep_lidar_info['is_key_frame'] = sweep_lidar_data[
                            'is_key_frame']
                        sweep_lidar_info['filename'] = sweep_lidar_data[
                            'filename']
                        sweep_lidar_info['calibrated_sensor'] = nusc.get(
                            'calibrated_sensor',
                            cam_data['calibrated_sensor_token'])
                        lidar_sweeps[j][lidar_names[k]] = sweep_lidar_info
            # Remove empty sweeps.
            for i, sweep in enumerate(cam_sweeps):
                if len(sweep.keys()) == 0:
                    cam_sweeps = cam_sweeps[:i]
                    break
            for i, sweep in enumerate(lidar_sweeps):
                if len(sweep.keys()) == 0:
                    lidar_sweeps = lidar_sweeps[:i]
                    break
            info['cam_sweeps'] = cam_sweeps
            info['lidar_sweeps'] = lidar_sweeps
            ann_infos = list()

            if 'anns' in cur_sample:
                for ann in cur_sample['anns']:
                    ann_info = nusc.get('sample_annotation', ann)
                    velocity = nusc.box_velocity(ann_info['token'])
                    if np.any(np.isnan(velocity)):
                        velocity = np.zeros(3)
                    ann_info['velocity'] = velocity
                    ann_infos.append(ann_info)
                info['ann_infos'] = ann_infos
            infos.append(info)
            if cur_sample['next'] == '':
                break
            else:
                cur_sample = nusc.get('sample', cur_sample['next'])
    return infos

import os
def gen_infos(nuscenes_base):
    trainval_nusc = NuScenes(version='v1.0-trainval',
                             dataroot=nuscenes_base, #'./data/nuScenes/',
                             verbose=True)
    train_scenes = splits.train #700
    val_scenes = splits.val #150
    train_infos_tiny = generate_info(trainval_nusc, train_scenes[:2])
    dump(train_infos_tiny, os.path.join(nuscenes_base, 'nuscenes_infos_train-tiny.pkl'))
    train_infos = generate_info(trainval_nusc, train_scenes)
    dump(train_infos, os.path.join(nuscenes_base,'nuscenes_infos_train.pkl'))
    val_infos = generate_info(trainval_nusc, val_scenes)
    dump(val_infos, os.path.join(nuscenes_base,'nuscenes_infos_val.pkl'))
    

    # test_nusc = NuScenes(version='v1.0-test',
    #                      dataroot='./data/nuScenes/v1.0-test/',
    #                      verbose=True)
    # test_scenes = splits.test
    # test_infos = generate_info(test_nusc, test_scenes)
    # mmcv.dump(test_infos, './data/nuScenes/nuscenes_infos_test.pkl')


# https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/nuscenes.py#L834
def map_pointcloud_to_image(
    pc,
    im,
    cam_calibrated_sensor,
    cam_ego_pose,
    min_dist: float = 0.0,
):
    pc = LidarPointCloud(pc)

    # Third step: transform from global into the ego vehicle
    # frame for the timestamp of the image.
    pc.translate(-np.array(cam_ego_pose['translation']))
    pc.rotate(Quaternion(cam_ego_pose['rotation']).rotation_matrix.T)

    # Fourth step: transform from ego into the camera.
    pc.translate(-np.array(cam_calibrated_sensor['translation']))
    pc.rotate(Quaternion(cam_calibrated_sensor['rotation']).rotation_matrix.T)

    # Fifth step: actually take a "picture" of the point cloud.
    # Grab the depths (camera frame z axis points away from the camera).
    depths = pc.points[2, :]
    coloring = depths

    # Take the actual picture (matrix multiplication with camera-matrix
    # + renormalization).
    points = view_points(pc.points[:3, :],
                         np.array(cam_calibrated_sensor['camera_intrinsic']),
                         normalize=True)

    # Remove points that are either outside or behind the camera.
    # Leave a margin of 1 pixel for aesthetic reasons. Also make
    # sure points are at least 1m in front of the camera to avoid
    # seeing the lidar points on the camera casing for non-keyframes
    # which are slightly out of sync.
    mask = np.ones(depths.shape[0], dtype=bool)
    mask = np.logical_and(mask, depths > min_dist)
    mask = np.logical_and(mask, points[0, :] > 1)
    mask = np.logical_and(mask, points[0, :] < im.shape[1] - 1)
    mask = np.logical_and(mask, points[1, :] > 1)
    mask = np.logical_and(mask, points[1, :] < im.shape[0] - 1)
    points = points[:, mask]
    coloring = coloring[mask]

    return points, coloring


#data_root = "/data/cmpe249-fa23/nuScenes/v1.0-trainval" #'data/nuScenes'
INFO_PATHS = ['nuscenes_infos_train.pkl',
              'nuscenes_infos_val.pkl']

lidar_key = 'LIDAR_TOP'
cam_keys = [
    'CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT', 'CAM_BACK_RIGHT',
    'CAM_BACK', 'CAM_BACK_LEFT'
]


def gen_depth_gt_worker(info, data_root):
    lidar_path = info['lidar_infos'][lidar_key]['filename']
    points = np.fromfile(os.path.join(data_root, lidar_path),
                         dtype=np.float32,
                         count=-1).reshape(-1, 5)[..., :4]
    lidar_calibrated_sensor = info['lidar_infos'][lidar_key][
        'calibrated_sensor']
    lidar_ego_pose = info['lidar_infos'][lidar_key]['ego_pose']

    # Points live in the point sensor frame. So they need to be
    # transformed via global to the image plane.
    # First step: transform the pointcloud to the ego vehicle
    # frame for the timestamp of the sweep.

    pc = LidarPointCloud(points.T)
    pc.rotate(Quaternion(lidar_calibrated_sensor['rotation']).rotation_matrix)
    pc.translate(np.array(lidar_calibrated_sensor['translation']))

    # Second step: transform from ego to the global frame.
    pc.rotate(Quaternion(lidar_ego_pose['rotation']).rotation_matrix)
    pc.translate(np.array(lidar_ego_pose['translation']))

    for i, cam_key in enumerate(cam_keys):
        cam_calibrated_sensor = info['cam_infos'][cam_key]['calibrated_sensor']
        cam_ego_pose = info['cam_infos'][cam_key]['ego_pose']
        img = mmcv.imread(
            os.path.join(data_root, info['cam_infos'][cam_key]['filename']))
        pts_img, depth = map_pointcloud_to_image(
            pc.points.copy(), img, cam_calibrated_sensor, cam_ego_pose)
        file_name = os.path.split(info['cam_infos'][cam_key]['filename'])[-1]
        np.concatenate([pts_img[:2, :].T, depth[:, None]],
                       axis=1).astype(np.float32).flatten().tofile(
                           os.path.join(data_root, 'depth_gt',
                                        f'{file_name}.bin'))
    # plt.savefig(f"{sample_idx}")


def gen_depth_gt(data_root, multi_thread=True):
    # po = Pool(24)
    # mmcv.mkdir_or_exist(os.path.join(data_root, 'depth_gt'))
    # for info_path in INFO_PATHS:
    #     info_path = os.path.join(data_root, info_path)
    #     infos = mmcv.load(info_path)
    #     for info in infos:
    #         po.apply_async(func=worker, args=(info, ))
    # po.close()
    # po.join()

    mmengine.mkdir_or_exist(os.path.join(data_root, 'depth_gt'))
    if multi_thread == True:
        po = Pool(24)
        for info_path in INFO_PATHS:
            info_path = os.path.join(data_root, info_path)
            infos = mmengine.load(info_path) #each train.pkl =>28130infos
            for info in infos:
                #gen_depth_gt_worker(info=info, data_root=data_root)
                po.apply_async(func=gen_depth_gt_worker, args=(info, data_root))
        po.close()
        po.join()
    else:
        for info_path in INFO_PATHS:
            info_path = os.path.join(data_root, info_path)
            infos = mmengine.load(info_path) #each train.pkl =>28130infos
            for info in infos:
                gen_depth_gt_worker(info=info, data_root=data_root)
    
    print("Finished gt worker")

DEBUG = False
if DEBUG:
    import matplotlib.pyplot as plt
    from nuscenes.utils.data_classes import LidarPointCloud
RADAR_CHAN = ['RADAR_FRONT', 'RADAR_FRONT_LEFT', 'RADAR_FRONT_RIGHT',
              'RADAR_BACK_LEFT', 'RADAR_BACK_RIGHT']

N_SWEEPS = 8
MIN_DISTANCE = 0.1
MAX_DISTANCE = 100.

DISABLE_FILTER = False

# https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/utils/data_classes.py#L315
# FIELDS: x y z dyn_prop id rcs vx vy vx_comp vy_comp is_quality_valid ambig_state 
#         x_rms y_rms invalid_state pdh0 vx_rms vy_rms
SAVE_FIELDS = [0, 1, 2, 5, 8, 9, -1]  # x, y, z, rcs, vx_comp, vy_comp, (dummy field for sweep info)
if DISABLE_FILTER:
    # use all point
    invalid_states = list(range(18))
    dynprop_states = list(range(8))
    ambig_states = list(range(5))
else:
    # use filtered point by invalid states and ambiguity status
    invalid_states = [0, 4, 8, 9, 10, 11, 12, 15, 16, 17]
    dynprop_states = list(range(8))
    ambig_states = [3]

def gen_radar_bev_worker(info, nusc, DATA_PATH, OUT_PATH):

    file_name = os.path.split(info['lidar_infos']['LIDAR_TOP']['filename'])[-1]
    output_file_name = os.path.join(DATA_PATH, OUT_PATH, file_name)
    if os.path.exists(output_file_name):
        print("File already exists:", output_file_name)
    else: #create the new file
        # Init.
        points = np.zeros((18, 0))
        all_pc = RadarPointCloud(points)

        sample = nusc.get('sample', info['lidar_infos']['LIDAR_TOP']['sample_token']) #dict, 'data' key contains all sensor data
        lidar_data = info['lidar_infos']['LIDAR_TOP'] #dict with lidar file name
        ref_pose_rec = nusc.get('ego_pose', lidar_data['ego_pose']['token']) #rotation, translation
        ref_cs_rec = nusc.get('calibrated_sensor', lidar_data['calibrated_sensor']['token'])
        ref_time = 1e-6 * lidar_data['timestamp']
        # Homogeneous transform from ego car frame to reference frame
        ref_from_car = transform_matrix(ref_cs_rec['translation'],
                                        Quaternion(ref_cs_rec['rotation']), inverse=True) #(4,4)
        # Homogeneous transformation matrix from global to _current_ ego car frame
        car_from_global = transform_matrix(ref_pose_rec['translation'],
                                        Quaternion(ref_pose_rec['rotation']), inverse=True) #(4,4)

        if DEBUG:
            lidar = LidarPointCloud.from_file(os.path.join(nusc.dataroot, lidar_data['filename']))

        for chan in RADAR_CHAN: #5 different Radars
            # Aggregate current and previous sweeps.
            sample_data_token = sample['data'][chan]
            current_sd_rec = nusc.get('sample_data', sample_data_token)
            for sweep in range(N_SWEEPS):
                # Load up the pointcloud and remove points close to the sensor.
                file_name = os.path.join(nusc.dataroot, current_sd_rec['filename'])#/data/cmpe249-fa23/nuScenes/v1.0-trainval/samples/RADAR_FRONT/xxx.pcd
                current_pc = RadarPointCloud.from_file(file_name, invalid_states, dynprop_states, ambig_states) #points field, (18, 77)

                # Get past pose.
                current_pose_rec = nusc.get('ego_pose', current_sd_rec['ego_pose_token'])
                global_from_car = transform_matrix(current_pose_rec['translation'],
                                                Quaternion(current_pose_rec['rotation']), inverse=False)

                # Homogeneous transformation matrix from sensor coordinate frame to ego car frame.
                current_cs_rec = nusc.get('calibrated_sensor', current_sd_rec['calibrated_sensor_token'])
                car_from_current = transform_matrix(current_cs_rec['translation'], Quaternion(current_cs_rec['rotation']),
                                                    inverse=False)

                # Fuse four transformation matrices into one and perform transform.
                trans_matrix = reduce(np.dot, [ref_from_car, car_from_global, global_from_car, car_from_current])
                current_pc.transform(trans_matrix)

                # Add time vector which can be used as a temporal feature.
                time_lag = ref_time - 1e-6 * current_sd_rec['timestamp']  # Positive difference.

                # Rotate velocity to reference frame
                velocities = current_pc.points[8:10, :]  # Compensated velocity
                velocities = np.vstack((velocities, np.zeros(current_pc.points.shape[1])))
                velocities = np.dot(Quaternion(current_cs_rec['rotation']).rotation_matrix, velocities)
                velocities = np.dot(Quaternion(ref_cs_rec['rotation']).rotation_matrix.T, velocities)
                current_pc.points[8:10, :] = velocities[0:2, :]

                # Compensate points on moving object by velocity of point
                current_pc.points[0, :] += current_pc.points[8, :] * time_lag
                current_pc.points[1, :] += current_pc.points[9, :] * time_lag

                # Save sweep index to unused field
                current_pc.points[-1, :] = sweep #(11,77)=>(18,77)

                # Merge with key pc.
                all_pc.points = np.hstack((all_pc.points, current_pc.points))

                # Abort if there are no previous sweeps.
                if current_sd_rec['prev'] == '':
                    break
                else:
                    current_sd_rec = nusc.get('sample_data', current_sd_rec['prev'])

        points = all_pc.points[SAVE_FIELDS, :].T.astype(np.float32) #(18, 392)=>(7, 392)=>(392,7)

        dist = np.linalg.norm(points[:, 0:2], axis=1) #(392,)
        mask = np.ones(dist.shape[0], dtype=bool) #(392,)
        mask = np.logical_and(mask, dist > MIN_DISTANCE) #0.1
        mask = np.logical_and(mask, dist < MAX_DISTANCE) #100
        points = points[mask, :] #(381, 7)

        
        points.tofile(output_file_name) #save pcd.bin file to radar_bev_filter
        print("Saved to file:", output_file_name)

def gen_radar_bev(data_root, OUT_PATH = 'radar_bev_filter', multi_thread = False):

    SPLIT = 'v1.0-trainval'
    nusc = NuScenes(version=SPLIT, dataroot=data_root, verbose=True)
    mmengine.mkdir_or_exist(os.path.join(data_root, OUT_PATH))
    if multi_thread == True:
        po = Pool(24)
        for info_path in INFO_PATHS:
            info_path = os.path.join(data_root, info_path)
            infos = mmengine.load(info_path) #each train.pkl =>28130infos
            for info in infos:
                po.apply_async(func=gen_radar_bev_worker, args=(info, nusc, data_root, OUT_PATH))
        po.close()
        po.join()
    else:
        for info_path in INFO_PATHS:
            info_path = os.path.join(data_root, info_path)
            infos = mmengine.load(info_path)
            for info in tqdm(infos):
                gen_radar_bev_worker(info, nusc, data_root, OUT_PATH)
    print('Finished')

def main():
    nuscenes_base="/data/cmpe249-fa23/nuScenes/v1.0-trainval"
    #gen_infos(nuscenes_base)##generate infos_val.pkl in /data/cmpe249-fa23/nuScenes/v1.0-trainval
    #gen_depth_gt(nuscenes_base)#generate jpg.bin in /data/cmpe249-fa23/nuScenes/v1.0-trainval/depth_gt/

    gen_radar_bev(nuscenes_base, OUT_PATH = 'radar_bev_filter')


if __name__ == '__main__':
    main()