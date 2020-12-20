import sys
from typing import Union

import supervisely_lib as sly
from tqdm import tqdm

from similarity_scorer.utils.logger import Logger
from .bounding_box_checker import BoundingBoxChecker
from .label_checker import LabelChecker
from .segmentation_checker import SegmentationChecker
from .utils import safe_request, extract_geometry_type_from_job_name


class SanityChecker:
    def __init__(
        self,
        server_address: str,
        server_token: str,
        team_name: str,
        workspace_name: str,
        project_name: Union[tuple, str],
        dry_run: bool = False,
        verbose: bool = False,
    ):
        self.dry_run = dry_run
        self.verbose = verbose
        self.sly_api = None
        self.sly_team = None
        self.sly_workspace = None
        self.sly_projects = []
        self.sly_project_metas = {}  # The key is the respective project name
        self.datasets = {}  # The key is the respective project name
        self.jobs = []
        self.job_statistics = (
            {}
        )  # The key is the respective job name or a pseudo-job name

        if self.dry_run:
            Logger.log_warn("This is a DRYRUN, i.e., tags will not be uploaded.")
        if self.verbose:
            Logger.log_warn(
                "Verbose mode activated, i.e., all discovered issues will be printed."
            )

        self._initialize_supervisely(
            server_address, server_token, team_name, workspace_name, project_name
        )
        self._initialize_jobs()

    def __del__(self):
        if self.dry_run:
            Logger.log_warn("This was a DRYRUN, i.e., tags have not been uploaded.")

    def __str__(self):
        string = ""
        max_length_line = 0
        max_length_job_name = max(
            [len(job_name) for job_name in self.job_statistics] + [0]
        )
        for job_name, job_statistics in self.job_statistics.items():
            new_line = f'{job_name.ljust(max_length_job_name)} | discovered issues = {job_statistics["numberIssues"]}\n'
            string += new_line
            max_length_line = max(max_length_line, len(new_line))
        max_length_line -= 1  # Subtract new line break \n
        string = "-" * max_length_line + "\n" + string + "-" * max_length_line
        return string

    def run(self):
        for project in self.sly_projects:
            self._run_project(project, self.sly_project_metas[project.name])

    def _initialize_supervisely(
        self,
        server_address: str,
        server_token: str,
        team_name: str,
        workspace_name: str,
        project_names: Union[tuple, str],
    ):
        # From now on, only assume project_name to be a tuple
        if isinstance(project_names, str):
            project_names = (project_names,)

        self.sly_api = sly.Api(server_address, server_token)

        self.sly_team = safe_request(self.sly_api.team.get_info_by_name, team_name)
        if self.sly_team is None:
            Logger.log_error(f"Team {team_name} not found.")
            sys.exit(-1)
        else:
            Logger.log_info(f"Team: id={self.sly_team.id}, name={self.sly_team.name}")

        self.sly_workspace = safe_request(
            self.sly_api.workspace.get_info_by_name, self.sly_team.id, workspace_name
        )
        if self.sly_workspace is None:
            Logger.log_error(f"Workspace {workspace_name} not found.")
            sys.exit(-1)
        else:
            Logger.log_info(
                f"Workspace: id={self.sly_workspace.id}, name={self.sly_workspace.name}"
            )

        for project_name in project_names:
            sly_project = safe_request(
                self.sly_api.project.get_info_by_name,
                self.sly_workspace.id,
                project_name,
            )
            if sly_project is None:
                Logger.log_error(f"Project {project_name} not found.")
                sys.exit(-1)
            else:
                Logger.log_info(
                    f"Project: id={sly_project.id}, name={sly_project.name}"
                )
                self.sly_projects.append(sly_project)

            # This is used in several calls to the API, e.g., creating objects from JSON representation.
            project_meta_json = safe_request(
                self.sly_api.project.get_meta, sly_project.id
            )
            self.sly_project_metas[sly_project.name] = sly.ProjectMeta.from_json(
                project_meta_json
            )

            # Add "Issue" tag if it does not exist yet
            if LabelChecker.issue_tag_meta.name not in [
                tag["name"] for tag in project_meta_json["tags"]
            ]:
                self.sly_project_metas[sly_project.name] = self.sly_project_metas[
                    sly_project.name
                ].add_tag_meta(LabelChecker.issue_tag_meta)
                safe_request(
                    self.sly_api.project.update_meta,
                    sly_project.id,
                    self.sly_project_metas[sly_project.name].to_json(),
                )

            # Initialize datasets of this project
            self.datasets[sly_project.name] = []
            for dataset in safe_request(self.sly_api.dataset.get_list, sly_project.id):
                Logger.log_info(f"Dataset: id={dataset.id}, name={dataset.name}")
                self.datasets[sly_project.name].append(dataset)

    def _initialize_jobs(self):
        # We have to query the jobs twice since the Supervisely API does not provide the entities (assigned images) in
        #  the first API call "get_list()"
        # Fun fact: the functionality has only been added due to our feature request and broke their repo multiple times
        jobs = []
        for project in self.sly_projects:
            for dataset in self.datasets[project.name]:
                jobs += safe_request(
                    self.sly_api.labeling_job.get_list,
                    self.sly_team.id,
                    dataset_id=dataset.id,
                )

        for job in jobs:
            Logger.log_info(f"Job: id={job.id}, name={job.name}")
            self.jobs.append(
                safe_request(self.sly_api.labeling_job.get_info_by_id, job.id)
            )  # Query assigned images

            # ToDo: Workaround because the API does not fill out the field 'classes_to_label'
            geometry_type = extract_geometry_type_from_job_name(job.name)

            # Use CamelCase to match the API's convention when creating JSON dictionaries
            self.job_statistics[job.name] = {
                "geometryType": geometry_type,
                "numberIssues": 0,
            }

    def _get_image_job_names(self, image_name: str, geometry_type: str) -> list:
        # The image could be in multiple jobs. Also, filter for the requested label type.
        job_names = []
        for job in self.jobs:
            for job_image in job.entities:
                if (
                    job_image["name"] == image_name
                    and self.job_statistics[job.name]["geometryType"] == geometry_type
                ):
                    job_names.append(job.name)
        return job_names

    def _found_issue_in_jobless_image(
        self, project_name: str, dataset_name: str, geometry_type: str
    ):
        # Create pseudo job for "project - dataset - geometry" to account for images that are not assigned to any job
        pseudo_job_name = f"{project_name} - {dataset_name} - {geometry_type}"
        if pseudo_job_name not in self.job_statistics.keys():
            # Use CamelCase to match the API's convention when creating JSON dictionaries
            self.job_statistics[pseudo_job_name] = {
                "geometryType": geometry_type,
                "numberIssues": 0,
            }
        self.job_statistics[pseudo_job_name]["numberIssues"] += 1

    def _run_project(self, project, project_meta):
        for dataset in self.datasets[project.name]:
            self._run_dataset(dataset, project_meta, project.name)

    def _run_dataset(self, dataset, project_meta, project_name: str):
        # These are all images in the dataset
        images = safe_request(self.sly_api.image.get_list, dataset.id)

        with tqdm(
            total=len(images),
            desc=f"Processing dataset: {project_name} - {dataset.name}",
        ) as pbar:
            # Batch images to reduce the number of API calls
            for batch in sly.batched(images, batch_size=10):
                image_ids = [image.id for image in batch]
                annotations = safe_request(
                    self.sly_api.annotation.download_batch, dataset.id, image_ids
                )
                updated_annotations = {"image_ids": [], "annotations": []}

                # Iterate over images in batch
                for image in annotations:
                    # We use this object to update the labels. All checkers share the same instance.
                    updated_annotation = sly.Annotation.from_json(
                        image.annotation, project_meta
                    )
                    bounding_box_checker = BoundingBoxChecker(
                        image.image_name,
                        image.annotation["size"]["height"],
                        image.annotation["size"]["width"],
                        project_meta,
                        updated_annotation,
                        not self.dry_run,
                        self.verbose,
                    )
                    segmentation_checker = SegmentationChecker(
                        image.image_name,
                        image.annotation["size"]["height"],
                        image.annotation["size"]["width"],
                        project_meta,
                        updated_annotation,
                        not self.dry_run,
                        self.verbose,
                    )
                    bounding_box_job_names = self._get_image_job_names(
                        image.image_name, "rectangle"
                    )
                    segmentation_job_names = self._get_image_job_names(
                        image.image_name, "bitmap"
                    )

                    update_image = False
                    # Iterate over labels in current image
                    for label in image.annotation["objects"]:
                        # We do not convert to a SLY object since it is easier to operate with the JSON dictionary
                        if label["geometryType"] == "rectangle":
                            if not bounding_box_checker.run(label):
                                if bounding_box_job_names:
                                    for job_name in bounding_box_job_names:
                                        self.job_statistics[job_name][
                                            "numberIssues"
                                        ] += 1
                                else:
                                    self._found_issue_in_jobless_image(
                                        project_name, dataset.name, "rectangle"
                                    )
                            update_image = bounding_box_checker.is_annotation_updated
                        elif label["geometryType"] == "bitmap":
                            if not segmentation_checker.run(label):
                                if segmentation_job_names:
                                    for job_name in segmentation_job_names:
                                        self.job_statistics[job_name][
                                            "numberIssues"
                                        ] += 1
                                else:
                                    self._found_issue_in_jobless_image(
                                        project_name, dataset.name, "bitmap"
                                    )
                            update_image = segmentation_checker.is_annotation_updated
                        else:
                            Logger.log_warn(
                                f"Found unsupported geometry type: {label['geometryType']}"
                            )

                    if update_image:
                        if id(bounding_box_checker.updated_annotation) != id(
                            segmentation_checker.updated_annotation
                        ):
                            raise RuntimeError("Memory addresses do not match.")
                        updated_annotations["image_ids"].append(image.image_id)
                        updated_annotations["annotations"].append(
                            bounding_box_checker.updated_annotation
                        )
                    pbar.update(1)

                # Upload all annotations in the current batch if there are any
                if updated_annotations["image_ids"] and not self.dry_run:
                    safe_request(
                        self.sly_api.annotation.upload_anns,
                        updated_annotations["image_ids"],
                        updated_annotations["annotations"],
                    )
