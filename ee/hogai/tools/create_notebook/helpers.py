from enum import Enum

from posthog.models import Team, User

from products.notebooks.backend.models import Notebook

from ee.hogai.artifacts.manager import ArtifactManager
from ee.hogai.artifacts.types import StoredBlock, StoredNotebookArtifactContent
from ee.hogai.tools.create_notebook.parsing import parse_notebook_content_for_storage
from ee.hogai.tools.create_notebook.tiptap import blocks_to_tiptap_doc
from ee.models.assistant import AgentArtifact


class ArtifactStatus(Enum):
    CREATED = "created"
    UPDATED = "updated"
    FAILED_TO_UPDATE = "failed_to_update"


async def create_or_update_notebook_artifact(
    artifacts_manager: ArtifactManager,
    content: str,
    title: str,
    artifact_id: str | None = None,
) -> tuple[AgentArtifact, ArtifactStatus]:
    """
    Parse markdown content and create or update a notebook artifact.

    Args:
        artifacts_manager: The ArtifactManager instance to use for persistence
        content: Markdown content with optional <insight>artifact_id</insight> tags
        title: Title for the notebook artifact
        artifact_id: Optional ID of existing artifact to update

    Returns:
        tuple[AgentArtifact, ArtifactStatus] with the artifact and status
    """
    blocks = parse_notebook_content_for_storage(content, title=title)
    artifact_content = StoredNotebookArtifactContent(blocks=blocks, title=title)

    artifact = None
    status = ArtifactStatus.CREATED

    if artifact_id:
        try:
            artifact = await artifacts_manager.aupdate(artifact_id, artifact_content)
            status = ArtifactStatus.UPDATED
        except ValueError:
            status = ArtifactStatus.FAILED_TO_UPDATE

    if not artifact:
        artifact = await artifacts_manager.acreate(content=artifact_content, name=title)
        if status != ArtifactStatus.FAILED_TO_UPDATE:
            status = ArtifactStatus.CREATED

    return artifact, status


async def save_notebook_to_db(
    team: Team,
    user: User,
    artifact: AgentArtifact,
    blocks: list[StoredBlock],
    title: str,
) -> Notebook:
    """
    Save or update a real Notebook record with the same short_id as the artifact.

    If a Notebook with the artifact's short_id already exists, update its content.
    Otherwise, create a new Notebook.
    """

    def resolve_visualization(artifact_id: str) -> dict | None:
        # Synchronous resolution -- we need to fetch viz data from the artifact manager
        # Since we're in async context, this uses the sync ORM directly
        try:
            viz_artifact = AgentArtifact.objects.get(short_id=artifact_id, team=team)
        except AgentArtifact.DoesNotExist:
            return None

        data = viz_artifact.data
        if data.get("content_type") != "visualization":
            return None

        query = data.get("query")
        name = data.get("name")
        if not query:
            return None

        # Build the notebook query node shape matching frontend's castAssistantQuery logic
        kind = query.get("kind", "")
        if kind == "HogQLQuery" or "HogQL" in kind:
            notebook_query = {"kind": "DataVisualizationNode", "source": query}
        else:
            notebook_query = {"kind": "InsightVizNode", "source": query}

        return {"query": notebook_query, "name": name}

    tiptap_doc = blocks_to_tiptap_doc(blocks, title=title, resolve_visualization=resolve_visualization)

    try:
        notebook = await Notebook.objects.aget(team=team, short_id=artifact.short_id)
        notebook.content = tiptap_doc
        notebook.title = title
        notebook.last_modified_by = user
        await notebook.asave(update_fields=["content", "title", "last_modified_by", "last_modified_at"])
    except Notebook.DoesNotExist:
        notebook = await Notebook.objects.acreate(
            short_id=artifact.short_id,
            team=team,
            created_by=user,
            last_modified_by=user,
            title=title,
            content=tiptap_doc,
        )

    return notebook


async def notebook_exists_for_artifact(team: Team, short_id: str) -> bool:
    return await Notebook.objects.filter(team=team, short_id=short_id).aexists()
