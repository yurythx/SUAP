from ninja import Schema


class DispositivoRegistroSchema(Schema):
    dispositivo_id: str
    ip_maquina: str


class HeartbeatSchema(Schema):
    id: int
    device_id: str
    version: str
    ip: str
    uptime: int


class ArtifactSchema(Schema):
    component: str
    url: str | None = None
    checksum: str | None = None


class UpdateResponseSchema(Schema):
    update_available: bool
    device_id: str | None = None
    version: str | None = None
    artifacts: list[ArtifactSchema] | None = None


class CheckResponseSchema(Schema):
    update_available: bool
    deploy_id: int | None = None
    version: str | None = None
    artifacts: list[ArtifactSchema] | None = None


class UpdateReportSchema(Schema):
    fleet_id: int
    deploy_id: int
    device_id: str
    version: str
    status: str


class StatusResponseSchema(Schema):
    status: str


class DeployResponseSchema(StatusResponseSchema):
    deployment_id: int | None = None


class DeployDispositivosResponseSchema(Schema):
    dispositivos: list[str]


class RegistrarResponseSchema(Schema):
    dispositivo_id: str
    registered: bool


class BatchHeartbeatSchema(Schema):
    heartbeats: list[HeartbeatSchema]


class BatchUpdateReportSchema(Schema):
    reports: list[UpdateReportSchema]
