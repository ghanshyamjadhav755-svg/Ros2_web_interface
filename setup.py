# ~/ros2_ws/src/amr_webserver/setup.py
from setuptools import setup, find_packages
from glob import glob
import os

package_name = 'amr_webserver'

setup(
    name=package_name,
    version='2.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'web'), glob('web/*.html')),
        (os.path.join('share', package_name, 'web/js'), glob('web/js/*.js')),
        (os.path.join('share', package_name, 'web/css'), glob('web/css/*.css')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='JD',
    maintainer_email='jd@example.com',
    description='Industrial-grade AMR WebServer with URDF, Map, Camera',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'websocket_bridge = amr_webserver.ros2_websocket_bridge:main',
            'websocket_bridge_enhanced = amr_webserver.ros2_websocket_bridge_enhanced:main',
            'http_server = amr_webserver.http_server:main',
        ],
    },
)