@Entry
@Component
struct Index {
  @State message: string = '快速入门';

  build() {
    Column() {
      Text(this.message)
        .fontSize(24)
        .fontWeight(700)
        .width('100%')
        .textAlign(TextAlign.Start)
        .padding({ left: 16 })
        .fontFamily('HarmonyHeiTi-Bold')
        .lineHeight(33)
      Banner()
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F1F3F5')
  }
}

@Preview
@Component
struct Banner {
  build() {
    Image($r('app.media.banner_pic1'))
      .objectFit(ImageFit.Contain)
      .width('100%')
      .padding({ top: 11, left: 16, right: 16 })
      .borderRadius(16)
  }
}