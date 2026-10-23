// Cesium 场景适配层：集中封装三维实体、建筑图层、相机和底图操作。
import * as Cesium from 'cesium'
import { simplifyForDisplay } from './geometry'
import { ROUTE_LEGENDS } from './types'
import type {
  BuildingRecord,
  BuildingSelection,
  PreparedTrack,
  RouteColorMode,
  RoutePoint,
} from './types'

const ROUTE_HEIGHT = 5

function position(point: RoutePoint, height = ROUTE_HEIGHT): Cesium.Cartesian3 {
  // Cesium 使用经度、纬度和高度创建三维笛卡尔坐标。
  return Cesium.Cartesian3.fromDegrees(point.longitude, point.latitude, height)
}

function routeColor(point: RoutePoint, mode: RouteColorMode): string {
  // 根据当前轨迹点的配速或心率，选择对应图例颜色。
  const legend = ROUTE_LEGENDS[mode]
  if (mode === 'plain') return legend[0]!.color
  const value = mode === 'pace' ? point.paceSeconds : point.heartRate
  if (value == null) return legend[3]!.color
  const boundaries = mode === 'pace' ? [270, 360] : [145, 170]
  return legend[value < boundaries[0]! ? 0 : value < boundaries[1]! ? 1 : 2]!.color
}

/**
 * 封装 Cesium 的命令式 API。Vue 管控界面状态，本类仅负责场景、图层和相机。
 * Viewer 不放入 reactive/ref，避免 Vue 深度代理 Cesium 内部对象。
 */
export class RegionScene {
  private viewer: Cesium.Viewer
  private routes = new Cesium.CustomDataSource('running-route')
  private buildings: Cesium.GeoJsonDataSource | undefined
  private runner: Cesium.Entity | undefined
  private trail: Cesium.Entity | undefined
  private track: PreparedTrack | undefined
  private trailPoints: RoutePoint[] = []
  private buildingVersion = 0
  private destroyed = false
  private basemap: Cesium.ImageryLayer | undefined
  private removeBasemapListener: (() => void) | undefined
  private cleanups: Array<() => void> = []

  constructor(
    container: HTMLElement,
    onSelect: (building: BuildingSelection | null) => void,
    onError: (message: string) => void,
  ) {
    this.viewer = new Cesium.Viewer(container, {
      // 默认用本地纯色地球。在线瓦片不可用时，建筑和轨迹仍能独立工作。
      baseLayer: false,
      baseLayerPicker: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      infoBox: false,
      skyBox: false,
      skyAtmosphere: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
    })
    this.viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#101b2a')
    this.viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#1c3040')
    this.viewer.scene.globe.enableLighting = false
    void this.viewer.dataSources.add(this.routes)

    this.cleanups.push(
      this.viewer.selectedEntityChanged.addEventListener((entity) => {
        const properties = entity?.properties?.getValue(this.viewer.clock.currentTime)
        onSelect(
          properties?.kind === 'building'
            ? { name: String(properties.name || '未命名建筑'), height: Number(properties.height_m) }
            : null,
        )
      }),
      this.viewer.scene.renderError.addEventListener((_scene, error) => {
        console.error('区域探索渲染失败：', error)
        onError('三维渲染中断，请刷新重试；若开启了在线底图，可先关闭后重新进入。')
      }),
    )
    this.viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(113.34, 23.14, 30_000),
    })
  }

  setRoute(track: PreparedTrack, mode: RouteColorMode): void {
    // 清空旧路线后按相邻采样点绘制彩色线段。
    this.track = track
    this.routes.entities.removeAll()
    this.trailPoints = simplifyForDisplay(track.points, 350)
    const points = simplifyForDisplay(track.points, 160)

    // 控制分段数量：一条长轨迹最多绘制约 160 段，颜色取各段起点的采样指标。
    for (let index = 1; index < points.length; index += 1) {
      const color = Cesium.Color.fromCssColorString(routeColor(points[index - 1]!, mode))
      this.routes.entities.add({
        polyline: {
          positions: [position(points[index - 1]!), position(points[index]!)],
          width: 5,
          material: new Cesium.PolylineGlowMaterialProperty({ color, glowPower: 0.15 }),
          depthFailMaterial: color.withAlpha(0.35),
        },
      })
    }

    this.trail = this.routes.entities.add({
      polyline: { positions: [], width: 2, material: Cesium.Color.WHITE },
    })
    for (const [index, name, color] of [
      [0, '起点', '#58dec5'],
      [track.points.length - 1, '终点', '#ff7870'],
    ] as const) {
      this.routes.entities.add({
        name,
        position: position(track.points[index]!, 8),
        point: { pixelSize: 9, color: Cesium.Color.fromCssColorString(color) },
        label: {
          text: name,
          font: '12px sans-serif',
          pixelOffset: new Cesium.Cartesian2(0, -20),
          disableDepthTestDistance: Infinity,
        },
      })
    }
    this.runner = this.routes.entities.add({
      name: '回放位置',
      position: position(track.points[0]!, 9),
      point: {
        pixelSize: 13,
        color: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.fromCssColorString('#58dec5'),
        outlineWidth: 4,
        disableDepthTestDistance: Infinity,
      },
    })
    this.viewer.scene.requestRender()
  }

  clearRoute(): void {
    this.track = undefined
    this.runner = undefined
    this.trail = undefined
    this.routes.entities.removeAll()
    this.setFollowing(false)
    this.viewer.scene.requestRender()
  }

  updateRunner(point: RoutePoint, following: boolean): void {
    // 更新回放标记和已完成轨迹；following 开启时相机跟随运动点。
    if (!this.runner || !this.trail?.polyline) return
    this.runner.position = new Cesium.ConstantPositionProperty(position(point, 9))
    const completed = this.trailPoints.filter((item) => item.elapsedSeconds <= point.elapsedSeconds)
    this.trail.polyline.positions = new Cesium.ConstantProperty([
      ...completed.map((item) => position(item, 6)),
      position(point, 6),
    ])
    if (following) {
      this.viewer.camera.cancelFlight()
      this.viewer.camera.lookAt(
        position(point),
        new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-38), 650),
      )
    }
    this.viewer.scene.requestRender()
  }

  setFollowing(enabled: boolean): void {
    if (!enabled) this.viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)
  }

  overview(): void {
    if (!this.track) return
    this.setFollowing(false)
    const sphere = Cesium.BoundingSphere.fromPoints(
      simplifyForDisplay(this.track.points).map((point) => position(point)),
    )
    this.viewer.camera.flyToBoundingSphere(sphere, {
      duration: 0.8,
      offset: new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(-20),
        Cesium.Math.toRadians(-48),
        Math.max(1000, sphere.radius * 3),
      ),
    })
  }

  async setBuildings(records: BuildingRecord[], scale: number, show: boolean): Promise<void> {
    // GeoJSON 加载是异步的，因此用版本号确保旧请求不会覆盖新场景。
    const version = ++this.buildingVersion
    const data = await Cesium.GeoJsonDataSource.load(
      {
        type: 'FeatureCollection',
        features: records.map((record, index) => ({
          ...record.feature,
          id: `building-${index}`,
          properties: {
            kind: 'building',
            name: record.feature.properties.name,
            height_m: record.height,
          },
        })),
      },
      { clampToGround: false },
    )

    // 旧请求完成时，用户可能已切换活动或离开页面，不能再修改已销毁的 Viewer。
    if (this.destroyed || version !== this.buildingVersion) return
    data.show = show
    for (const entity of data.entities.values) {
      if (!entity.polygon) continue
      const height = Number(entity.properties?.height_m?.getValue())
      entity.polygon.height = new Cesium.ConstantProperty(0)
      entity.polygon.extrudedHeight = new Cesium.ConstantProperty(height * scale)
      entity.polygon.outline = new Cesium.ConstantProperty(false)
      const color =
        height < 30 ? '#527d9b' : height < 80 ? '#6db6c5' : height < 150 ? '#eeb36d' : '#ff7870'
      entity.polygon.material = new Cesium.ColorMaterialProperty(
        Cesium.Color.fromCssColorString(color).withAlpha(0.9),
      )
    }
    await this.viewer.dataSources.add(data)
    if (this.destroyed) return
    if (version !== this.buildingVersion) {
      this.viewer.dataSources.remove(data, true)
      return
    }
    this.clearBuildingLayer()
    this.buildings = data
    this.viewer.scene.requestRender()
  }

  clearBuildings(): void {
    this.buildingVersion += 1
    this.clearBuildingLayer()
  }

  private clearBuildingLayer(): void {
    this.viewer.selectedEntity = undefined
    if (this.buildings) this.viewer.dataSources.remove(this.buildings, true)
    this.buildings = undefined
  }

  updateBuildingStyle(scale: number, show: boolean): void {
    if (!this.buildings) return
    this.buildings.show = show
    for (const entity of this.buildings.entities.values) {
      if (!entity.polygon) continue
      const height = Number(entity.properties?.height_m?.getValue())
      entity.polygon.extrudedHeight = new Cesium.ConstantProperty(height * scale)
    }
    this.viewer.scene.requestRender()
  }

  setBasemap(enabled: boolean, onUnavailable: () => void): void {
    this.removeBasemapListener?.()
    this.removeBasemapListener = undefined
    if (this.basemap) this.viewer.imageryLayers.remove(this.basemap, true)
    this.basemap = undefined
    if (!enabled) return
    const provider = new Cesium.OpenStreetMapImageryProvider({
      url: 'https://tile.openstreetmap.org/',
    })
    this.basemap = this.viewer.imageryLayers.addImageryProvider(provider)
    this.removeBasemapListener = provider.errorEvent.addEventListener(() => {
      if (this.destroyed || !this.basemap) return
      this.removeBasemapListener?.()
      this.removeBasemapListener = undefined
      this.viewer.imageryLayers.remove(this.basemap, true)
      this.basemap = undefined
      onUnavailable()
    })
  }

  resize(): void {
    this.viewer.resize()
    this.viewer.scene.requestRender()
  }

  destroy(): void {
    this.destroyed = true
    this.buildingVersion += 1
    this.removeBasemapListener?.()
    this.cleanups.forEach((cleanup) => cleanup())
    this.viewer.destroy()
  }
}
