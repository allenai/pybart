require.config({
    //By default load any module IDs from js/lib
    baseUrl: 'scripts'
});

require([
	'tag', 
	'jquery',
	'main',
], function(
	TAG,
	$,
	main
) {
	window.SVG.prepare();

	// Main function
	$(async () => {
	  // -----
	  // Fonts
	  // -----
	  // Because the demo uses an externally-loaded font, we use the Web Font
	  // Loader to ensure that it is available before initialisation (so that we
	  // can calculate the dimensions of SVG Text elements accurately)
	  const fontLoadPromise = new Promise((resolve, reject) => {
		WebFont.load({
		  google: {
			families: ["Nunito:600,700"]
		  },
		  active: () => {
			resolve();
		  }
		});
	  });

	  await fontLoadPromise;

	  main();
	  
	});
});