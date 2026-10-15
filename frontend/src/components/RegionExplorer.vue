<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'

const container = ref<HTMLDivElement>()
let viewer: Cesium.Viewer | undefined

const buildingsUrl = '/cesium-data/guangzhou-buildings.geojson'

async function initializeCesium(): Promise<void> {
  if (!container.value) return

  viewer = new Cesium.Viewer(container.value, {
    // 不使用 Cesium ion 默认影像，因此不需要 Token。
    baseLayer: new Cesium.ImageryLayer(
      new Cesium.OpenStreetMapImageryProvider({
        url: 'https://tile.openstreetmap.org/',
      }),
    ),

    baseLayerPicker: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    geocoder: false,
    homeButton: true,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: true,
    selectionIndicator: true,
  })

  const buildings = await Cesium.GeoJsonDataSource.load(buildingsUrl, {
    clampToGround: false,
  })

  await viewer.dataSources.add(buildings)

  for (const entity of buildings.entities.values) {
    if (!entity.polygon) continue

    const rawHeight = entity.properties?.height_m?.getValue()
    const height = Number(rawHeight)

    entity.polygon.height = new Cesium.ConstantProperty(0)
    entity.polygon.extrudedHeight = new Cesium.ConstantProperty(
      Number.isFinite(height) ? height : 10,
    )

    entity.polygon.material = new Cesium.ColorMaterialProperty(
      Cesium.Color.fromCssColorString('#f47a48').withAlpha(0.78),
    )
    entity.polygon.outline = new Cesium.ConstantProperty(true)
    entity.polygon.outlineColor = new Cesium.ConstantProperty(Cesium.Color.WHITE.withAlpha(0.35))
  }

  await viewer.flyTo(buildings)
}

onMounted(() => {
  initializeCesium()
})

onBeforeUnmount(() => {
  viewer?.destroy()
  viewer = undefined
})
</script>

<template>
  <section class="region-explorer">
    <div ref="container" class="cesium-container"></div>
  </section>
</template>

<style scoped>
.region-explorer {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.cesium-container {
  width: 100%;
  height: 100%;
  min-height: 500px;
}
</style>