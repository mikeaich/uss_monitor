.PHONY: push
push:
	adb root
	adb remount
	adb push ../../out/target/product/flame/system/bin/procserver /system/bin/procserver
